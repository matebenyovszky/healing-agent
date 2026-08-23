"""Provider sampling parameters are forwarded verbatim — and only when set.

Two properties matter here and they pull in opposite directions:

* a config that declares ``params`` must reach the provider unchanged, so a
  benchmark sweep can vary temperature, seed or ``num_ctx`` per run;
* a config that declares nothing must produce exactly the request earlier
  releases sent, so upgrading changes no one's results.

The second is the easy one to break: sending ``options: {}`` or
``temperature=None`` is not the same as sending nothing.
"""

import pytest

from healing_agent import ai_broker


class _FakeMessage:
    content = "  fixed code  "


class _FakeChoice:
    message = _FakeMessage()


class _FakeCompletion:
    choices = [_FakeChoice()]


def _fake_openai_client(captured):
    """A stand-in for openai.OpenAI / openai.AzureOpenAI recording call kwargs."""

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeCompletion()

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, **_kwargs):
            self.chat = _Chat()

    return _Client


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"response": "fixed code"}


# --- _params ----------------------------------------------------------------

def test_params_absent_or_empty_sends_nothing():
    assert ai_broker._params({}) == {}
    assert ai_broker._params({"params": {}}) == {}
    assert ai_broker._params({"params": None}) == {}


def test_params_are_copied_not_shared():
    block = {"params": {"temperature": 0.2}}
    result = ai_broker._params(block)
    result["temperature"] = 1.0
    assert block["params"]["temperature"] == 0.2


def test_malformed_params_are_ignored_rather_than_raising():
    # A misconfigured params entry must not become a failure inside the healing
    # path, where it would replace the application's own exception.
    assert ai_broker._params({"params": "temperature=0.2"}) == {}


# --- Ollama: params belong under "options" ----------------------------------

def test_ollama_omits_options_when_no_params(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse()

    monkeypatch.setattr(ai_broker.requests, "post", fake_post)
    ai_broker._get_ollama_response("prompt", {"host": "http://h", "model": "m"})

    assert "options" not in captured["json"]


def test_ollama_params_are_nested_under_options(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse()

    monkeypatch.setattr(ai_broker.requests, "post", fake_post)
    ai_broker._get_ollama_response(
        "prompt",
        {
            "host": "http://h",
            "model": "m",
            "params": {"temperature": 0.2, "seed": 7, "num_ctx": 8192},
        },
    )

    assert captured["json"]["options"] == {
        "temperature": 0.2,
        "seed": 7,
        "num_ctx": 8192,
    }
    # The sampling options must not leak into the top level of the payload.
    assert "temperature" not in captured["json"]


# --- OpenAI / Azure: params are request keyword arguments -------------------

def test_openai_forwards_params_as_request_kwargs(monkeypatch):
    captured = {}
    monkeypatch.setattr(ai_broker.openai, "OpenAI", _fake_openai_client(captured))

    ai_broker._get_openai_response(
        "prompt",
        {"api_key": "k", "model": "m", "params": {"temperature": 0.2, "seed": 7}},
        "system",
    )

    assert captured["temperature"] == 0.2
    assert captured["seed"] == 7


def test_openai_without_params_sends_no_sampling_arguments(monkeypatch):
    captured = {}
    monkeypatch.setattr(ai_broker.openai, "OpenAI", _fake_openai_client(captured))

    ai_broker._get_openai_response("prompt", {"api_key": "k", "model": "m"}, "system")

    assert set(captured) == {"model", "messages", "timeout"}


def test_azure_forwards_params_as_request_kwargs(monkeypatch):
    captured = {}
    monkeypatch.setattr(ai_broker.openai, "AzureOpenAI", _fake_openai_client(captured))

    ai_broker._get_azure_response(
        "prompt",
        {
            "api_key": "k",
            "api_version": "v",
            "endpoint": "e",
            "deployment_name": "d",
            "params": {"temperature": 0.0},
        },
        "system",
    )

    assert captured["temperature"] == 0.0


# --- Anthropic: params win over the block-level shorthands ------------------

def test_anthropic_params_override_the_temperature_shorthand(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    captured = {}

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)

            class _Block:
                text = "fixed code"

            class _Response:
                content = [_Block()]

            return _Response()

    class _Client:
        def __init__(self, **_kwargs):
            self.messages = _Messages()

    monkeypatch.setattr(anthropic, "Anthropic", _Client)

    ai_broker._get_anthropic_response(
        "prompt",
        {"api_key": "k", "model": "m", "temperature": 1.0, "params": {"temperature": 0.2}},
        "system",
    )

    assert captured["temperature"] == 0.2
