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
    import openai
    monkeypatch.setattr(openai, "OpenAI", _fake_openai_client(captured))

    ai_broker._get_openai_response(
        "prompt",
        {"api_key": "k", "model": "m", "params": {"temperature": 0.2, "seed": 7}},
        "system",
    )

    assert captured["temperature"] == 0.2
    assert captured["seed"] == 7


def test_openai_without_params_sends_no_sampling_arguments(monkeypatch):
    captured = {}
    import openai
    monkeypatch.setattr(openai, "OpenAI", _fake_openai_client(captured))

    ai_broker._get_openai_response("prompt", {"api_key": "k", "model": "m"}, "system")

    assert set(captured) == {"model", "messages", "timeout"}


def test_azure_forwards_params_as_request_kwargs(monkeypatch):
    captured = {}
    import openai
    monkeypatch.setattr(openai, "AzureOpenAI", _fake_openai_client(captured))

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


# --- Anthropic: one config, three SDK generations ----------------------------
#
# SDK 0.x takes sampling parameters as keyword arguments; 1.x removed them from
# the signature (a TypeError) but still sends them through extra_body on API
# version 2023-06-01; 2.x speaks 2026-10-21, which rejects them outright.

def _anthropic_capture(monkeypatch, version, content=None):
    anthropic = pytest.importorskip("anthropic")
    captured = {}

    class _Block:
        type = "text"
        text = "fixed code"

    class _Response:
        stop_reason = "end_turn"

    _Response.content = content if content is not None else [_Block()]

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Response()

    class _Client:
        def __init__(self, **_kwargs):
            self.messages = _Messages()

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    monkeypatch.setattr(anthropic, "__version__", version)
    monkeypatch.setattr(ai_broker, "_warned_dropped_sampling", False)
    return captured


def _anthropic_call(config):
    return ai_broker._get_anthropic_response(
        "prompt", {"api_key": "k", "model": "m", **config}, "system"
    )


def test_anthropic_0x_params_override_the_temperature_shorthand(monkeypatch):
    captured = _anthropic_capture(monkeypatch, "0.121.0")
    _anthropic_call({"temperature": 1.0, "params": {"temperature": 0.2}})
    assert captured["temperature"] == 0.2
    assert "extra_body" not in captured


def test_anthropic_1x_sends_sampling_through_extra_body(monkeypatch):
    captured = _anthropic_capture(monkeypatch, "1.17.0")
    _anthropic_call({"temperature": 0.2, "params": {"top_p": 0.9}})
    assert "temperature" not in captured and "top_p" not in captured
    assert captured["extra_body"] == {"temperature": 0.2, "top_p": 0.9}


def test_anthropic_2x_drops_sampling_and_says_so_once(monkeypatch):
    captured = _anthropic_capture(monkeypatch, "2.3.0")
    said = []
    monkeypatch.setattr(ai_broker, "emit", lambda message, **_kw: said.append(message))
    _anthropic_call({"temperature": 0.2})
    _anthropic_call({"temperature": 0.2})
    assert not {"temperature", "extra_body"} & set(captured)
    assert sum("2026-10-21" in message for message in said) == 1


@pytest.mark.parametrize("version", ["0.121.0", "1.17.0", "2.3.0"])
def test_anthropic_default_temperature_is_never_sent(monkeypatch, version):
    # The template's 1.0 is the API default, and Claude 4.7 and later reject
    # the field even at that value.
    captured = _anthropic_capture(monkeypatch, version)
    _anthropic_call({"temperature": 1.0})
    assert "temperature" not in captured and "extra_body" not in captured


def test_anthropic_reads_the_text_past_a_thinking_block(monkeypatch):
    class _Thinking:
        type = "thinking"
        thinking = ""

    class _Text:
        type = "text"
        text = "fixed code"

    _anthropic_capture(monkeypatch, "2.3.0", content=[_Thinking(), _Text()])
    assert _anthropic_call({}) == "fixed code"


def test_anthropic_without_text_names_the_stop_reason(monkeypatch):
    _anthropic_capture(monkeypatch, "2.3.0", content=[])
    with pytest.raises(ValueError, match="stop_reason"):
        _anthropic_call({})
