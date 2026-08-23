"""
GitHub issue escalation tests — no network, no API key required.

Escalation must be silent when disabled, deduplicate repeated failures, and
never replace the application's own exception with a reporting problem.
"""

import importlib
import json

import pytest

# The package replaces itself with a callable in sys.modules, so submodules
# must be imported by full path rather than as a package attribute.
github_issue = importlib.import_module("healing_agent.github_issue")
healing_module = importlib.import_module("healing_agent.healing_agent")


def _context(
    error_type="KeyError",
    message="'amount'",
    line="total += int(r[\"amount\"])",
    file_path="/repo/src/loader.py",
):
    return {
        "timestamp": "2026-08-23T21:00:00",
        "error": {
            "type": error_type,
            "message": message,
            "file": file_path,
            "line_number": 12,
            "error_line": line,
            "function_name": "load_sales",
        },
        "function_info": {"name": "load_sales", "qualname": "load_sales"},
        "ai_hint": "The amount column is missing.",
        "variables": {"locals": {"password": "<redacted>", "rows": "2 rows"}},
    }


def _github(**overrides):
    github = {"repo": "owner/name", "issue_on_failure": True}
    github.update(overrides)
    return {"GITHUB": github}


# --- fingerprint semantics ---------------------------------------------------

def test_message_normalization_collapses_numbers_but_keeps_identifiers():
    assert github_issue.normalize_message("row 5 failed") == "row N failed"
    assert github_issue.normalize_message("row 812 failed") == "row N failed"
    # Quoted identifiers carry real meaning and must survive verbatim.
    assert github_issue.normalize_message("'amount'") == "'amount'"


def test_same_failure_yields_the_same_fingerprint():
    assert github_issue.build_fingerprint(_context()) == github_issue.build_fingerprint(
        _context()
    )


def test_varying_row_numbers_share_one_fingerprint():
    first = _context(message="parse error on row 5")
    second = _context(message="parse error on row 812")
    assert github_issue.build_fingerprint(first) == github_issue.build_fingerprint(
        second
    )


def test_different_drifted_columns_are_different_failures():
    first = _context(message="'amount'")
    second = _context(message="'osszeg'")
    assert github_issue.build_fingerprint(first) != github_issue.build_fingerprint(
        second
    )


def test_fingerprint_survives_line_number_shifts():
    """The failing line TEXT identifies the failure, not its position."""
    moved = _context()
    moved["error"]["line_number"] = 97
    assert github_issue.build_fingerprint(moved) == github_issue.build_fingerprint(
        _context()
    )


# --- issue body by detail level ---------------------------------------------

def test_reference_level_uploads_no_captured_values():
    issue = github_issue.build_issue(
        _context(), _github(issue_detail="reference")
    )
    assert "KeyError" in issue["title"]
    assert "load_sales" in issue["title"]
    assert github_issue.FINGERPRINT_MARKER in issue["body"]
    assert "_healing_agent_exceptions/" in issue["body"]
    # No context attachment, so captured variable names stay local.
    assert "```json" not in issue["body"]
    assert "rows" not in issue["body"]


def test_redacted_level_attaches_the_context():
    issue = github_issue.build_issue(_context(), _github(issue_detail="redacted"))
    assert "```json" in issue["body"]
    assert "Redacted context" in issue["body"]
    assert "<redacted>" in issue["body"]


def test_attachment_is_size_capped(monkeypatch):
    monkeypatch.setattr(github_issue, "MAX_ATTACHMENT_CHARS", 200)
    context = _context()
    context["variables"]["locals"]["huge"] = "x" * 5000
    issue = github_issue.build_issue(context, _github(issue_detail="redacted"))
    assert "truncated" in issue["body"]
    assert len(issue["body"]) < 2000


# --- escalation behavior -----------------------------------------------------

def test_escalation_is_a_noop_when_disabled(monkeypatch):
    def fail(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("no network call expected when disabled")

    monkeypatch.setattr(github_issue, "_resolve_token", fail)
    assert (
        github_issue.open_issue_for_failure(
            _context(), _github(issue_on_failure=False)
        )
        is None
    )


def test_escalation_skips_without_a_token(monkeypatch):
    monkeypatch.setattr(github_issue, "_resolve_token", lambda _config: None)
    assert github_issue.open_issue_for_failure(_context(), _github()) is None


def test_duplicate_failure_does_not_open_a_second_issue(monkeypatch):
    import requests

    posted = []
    monkeypatch.setattr(github_issue, "_resolve_token", lambda _config: "t0ken")
    monkeypatch.setattr(
        github_issue,
        "find_existing_issue",
        lambda *_args, **_kwargs: "https://github.com/owner/name/issues/7",
    )
    monkeypatch.setattr(requests, "post", lambda *a, **k: posted.append(a))

    url = github_issue.open_issue_for_failure(_context(), _github())
    assert url == "https://github.com/owner/name/issues/7"
    assert posted == [], "a duplicate must not be posted"


def test_existing_issue_is_matched_by_fingerprint(monkeypatch):
    import requests

    fingerprint = github_issue.build_fingerprint(_context())

    class Response:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return [
                {"html_url": "https://x/1", "body": "unrelated failure"},
                {
                    "html_url": "https://x/2",
                    "body": f"<!-- {github_issue.FINGERPRINT_MARKER} {fingerprint} -->",
                },
            ]

    monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
    found = github_issue.find_existing_issue(
        "owner/name", "t0ken", fingerprint, "healing-agent"
    )
    assert found == "https://x/2"


def test_new_failure_opens_an_issue(monkeypatch):
    import requests

    sent = {}

    class Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"html_url": "https://github.com/owner/name/issues/42"}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["url"] = url
        sent["payload"] = json
        return Response()

    monkeypatch.setattr(github_issue, "_resolve_token", lambda _config: "t0ken")
    monkeypatch.setattr(
        github_issue, "find_existing_issue", lambda *_a, **_k: None
    )
    monkeypatch.setattr(requests, "post", fake_post)

    url = github_issue.open_issue_for_failure(_context(), _github())
    assert url == "https://github.com/owner/name/issues/42"
    assert sent["url"].endswith("/repos/owner/name/issues")
    assert sent["payload"]["labels"] == ["healing-agent"]
    assert github_issue.FINGERPRINT_MARKER in sent["payload"]["body"]


def test_escalation_never_raises_over_the_application_error(monkeypatch):
    import requests

    monkeypatch.setattr(github_issue, "_resolve_token", lambda _config: "t0ken")
    monkeypatch.setattr(github_issue, "find_existing_issue", lambda *_a, **_k: None)

    def explode(*_args, **_kwargs):
        raise ConnectionError("GitHub unreachable")

    monkeypatch.setattr(requests, "post", explode)
    assert github_issue.open_issue_for_failure(_context(), _github()) is None


def test_token_comes_from_the_configured_env_var(monkeypatch):
    monkeypatch.setenv("MY_CUSTOM_TOKEN", "from-env")
    config = _github(token_env="MY_CUSTOM_TOKEN")
    assert github_issue._resolve_token(config) == "from-env"


# --- wiring into the failure path -------------------------------------------

def test_failed_healing_escalates_the_first_context(tmp_path, monkeypatch):
    """The issue must describe the original error, not a later failure of the
    agent's own candidate."""
    escalated = []

    monkeypatch.setattr(
        healing_module,
        "open_issue_for_failure",
        lambda context, config: escalated.append(context) or "https://x/1",
    )
    monkeypatch.setattr(
        healing_module,
        "load_config",
        lambda: (
            {
                "MAX_ATTEMPTS": 1,
                "AUTO_FIX": True,
                "AUTO_SYSCHANGE": False,
                "BACKUP_ENABLED": True,
                "RESTORE_ON_FAILURE": True,
                "SAVE_EXCEPTIONS": False,
                "SAVE_AI_FIXES": False,
                "DEBUG": False,
                "GIT_MODE": "off",
                "GITHUB": {"issue_on_failure": True, "repo": "owner/name"},
            },
            None,
        ),
    )
    monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "hint")
    monkeypatch.setattr(
        healing_module,
        "fix",
        lambda *_a, **_k: 'def broken(value):\n    return value["still_missing"]\n',
    )

    module_path = tmp_path / "escalation_demo.py"
    module_path.write_text(
        'import healing_agent\n\n@healing_agent\ndef broken(value):\n'
        '    return value["missing"]\n',
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("escalation_demo", module_path)
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules["escalation_demo"] = module
    spec.loader.exec_module(module)

    with pytest.raises(Exception):
        module.broken({})

    assert len(escalated) == 1, "escalation should happen once per session"
    assert escalated[0]["error"]["message"] == "'missing'", (
        "escalation must report the original failure, not the candidate's"
    )
