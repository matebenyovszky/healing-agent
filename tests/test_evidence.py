"""
What evidence is captured, and what it is safe to do with it.

One redaction policy applies everywhere — names AND value shapes — so the same
evidence is safe on disk, in a prompt and in a GitHub issue. Only the SIZE
differs, and these tests pin both halves of that claim.
"""

import importlib
import json
import os

import pytest

redactor = importlib.import_module("healing_agent.redactor")
handler = importlib.import_module("healing_agent.exception_handler")
fixer = importlib.import_module("healing_agent.ai_code_fixer")
saver = importlib.import_module("healing_agent.exception_saver")
evidence = importlib.import_module("healing_agent.evidence")
github_issue = importlib.import_module("healing_agent.github_issue")


# --- value-level scrubbing ---------------------------------------------------

@pytest.mark.parametrize(
    "value,must_not_contain",
    [
        ("postgres://app:S3cr3t@db.internal/prod", "S3cr3t"),
        ("https://abc123def456@o1.ingest.sentry.io/42", "abc123def456"),
        ("https://ghp_abcdefghijklmnopqrst@github.com/o/r.git", "ghp_abcdefghij"),
        ("token is sk-abcdefghijklmnopqrstuvwx", "sk-abcdefghijklmnop"),
        ("AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.sIgNaTuRe", "sIgNaTuRe"),
        ("-----BEGIN RSA PRIVATE KEY-----", "BEGIN RSA PRIVATE KEY"),
    ],
)
def test_secrets_hiding_in_values_are_masked(value, must_not_contain):
    """Name-based redaction cannot see these: the NAME looks harmless."""
    assert must_not_contain not in redactor.scrub_value(value)


@pytest.mark.parametrize(
    "value",
    [
        "Europe/Budapest",
        "/usr/local/bin:/usr/bin",
        "https://api.example.com/v1",
        "production",
        "3.12.3",
    ],
)
def test_ordinary_values_survive_untouched(value):
    """Over-redaction would destroy the diagnostic value of the environment."""
    assert redactor.scrub_value(value) == value


# --- environment capture -----------------------------------------------------

def test_only_the_listed_variables_are_captured(monkeypatch):
    """An allowlist, not a filter: this is the security boundary.

    A denylist can only mask the secret shapes it already knows, so a bespoke
    secret under a harmless name would travel. Naming what you want inverts
    that — it is not captured because it was never asked for.
    """
    monkeypatch.setenv("EV_REGION", "eu-central-1")
    monkeypatch.setenv("EV_BESPOKE_SECRET", "shape-nobody-can-recognise")

    environment = handler.capture_environment({"ENVIRONMENT_VARS": ["EV_REGION"]})

    assert environment == {"EV_REGION": "eu-central-1"}
    assert "EV_BESPOKE_SECRET" not in environment


def test_listed_variables_are_still_filtered(monkeypatch):
    """Defence in depth: asking for a variable is not asking for its secret."""
    monkeypatch.setenv("EV_DB_URL", "postgres://app:S3cr3t@db/prod")
    monkeypatch.setenv("EV_API_KEY", "totally-secret")

    environment = handler.capture_environment(
        {"ENVIRONMENT_VARS": ["EV_DB_URL", "EV_API_KEY"]}
    )

    assert environment["EV_API_KEY"] == redactor.DEFAULT_PLACEHOLDER
    assert "S3cr3t" not in environment["EV_DB_URL"]
    assert "db/prod" in environment["EV_DB_URL"], "over-redacted the host"


def test_an_empty_list_captures_nothing(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert handler.capture_environment({"ENVIRONMENT_VARS": []}) == {}


def test_absent_variables_are_simply_missing(monkeypatch):
    monkeypatch.delenv("EV_NOT_SET", raising=False)
    assert handler.capture_environment({"ENVIRONMENT_VARS": ["EV_NOT_SET"]}) == {}


def test_environment_is_not_captured_when_no_sink_carries_it():
    """Reading the environment for nobody is waste, so capture follows policy."""
    nobody_wants_it = {
        "EVIDENCE": {sink: {"environment": 0} for sink in evidence.DEFAULT_EVIDENCE}
    }
    context = handler.capture_context(config=nobody_wants_it)
    assert "environment" not in context


def test_the_default_allowlist_is_used_when_none_is_configured(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    context = handler.capture_context(config={})
    assert context["environment"]["APP_ENV"] == "production"


def test_the_default_allowlist_is_small_and_obviously_non_secret():
    """A default that captured broadly would be a denylist by another name."""
    names = handler.DEFAULT_ENVIRONMENT_VARS
    assert len(names) < 20
    for name in names:
        assert not redactor.is_sensitive_name(
            name, redactor.get_sensitive_matcher()
        ), f"{name} should not be captured by default"


# --- size policy: rich on disk, affordable on the way out --------------------

def test_disk_carries_more_than_the_prompt_does():
    """Space on disk is nearly free; a prompt is paid for on every attempt."""
    disk = evidence.policy({}, "disk")
    provider = evidence.policy({}, "provider")
    assert disk["variables"] > provider["variables"]
    assert disk["logs"] > provider["logs"]


def test_trim_shortens_strings_at_every_depth():
    trimmed = evidence.trim_value(
        {"a": "x" * 100, "b": {"c": ["y" * 100]}, "n": 5}, 10
    )
    assert trimmed["a"].startswith("x" * 10) and len(trimmed["a"]) < 20
    assert len(trimmed["b"]["c"][0]) < 20
    assert trimmed["n"] == 5, "non-strings must pass through untouched"


def _context(**extra):
    context = {
        "function_info": {"name": "load", "source_code": "def load(): ...",
                          "signature": "()", "module": "demo"},
        "function_arguments": {},
        "error": {"type": "KeyError", "message": "'amount'", "line_number": 3,
                  "error_line": "row['amount']", "exception_attrs": {},
                  "traceback_frames": [], "traceback": "", "function_name": "load"},
    }
    context.update(extra)
    return context


def test_prompt_carries_state_and_environment_trimmed():
    context = _context(
        variables={"locals": {"rows": {"type": "list", "value_preview": "R" * 5000}}},
        environment={"APP_ENV": "production"},
    )
    prompt = fixer.prepare_fix_prompt(context, {"PROMPT_VALUE_CHARS": 50})

    assert "Local variables at the moment of failure" in prompt
    assert "APP_ENV=production" in prompt
    assert "R" * 5000 not in prompt, "the prompt was not trimmed"
    assert "R" * 50 in prompt


def test_disk_artifact_is_capped_but_still_written(tmp_path, monkeypatch):
    monkeypatch.setattr(saver, "MAX_ARTIFACT_BYTES", 2000)
    source = tmp_path / "demo.py"
    source.write_text("x = 1\n", encoding="utf-8")
    context = _context(variables={"locals": {"big": {"value_preview": "Z" * 50000}}})
    context["error"]["file"] = str(source)

    path = saver.save_context(context)

    assert path is not None, "an oversized context must still be saved"
    saved = json.loads(open(path, encoding="utf-8").read())
    assert "artifact_note" in saved, "the trim was not recorded"
    assert os.path.getsize(path) < 60000


# --- the issue carries the package by default -------------------------------

def test_issue_attaches_the_context_by_default():
    context = _context(
        variables={"locals": {"rows": {"type": "list", "value_preview": "2 rows"}}},
        environment={"APP_ENV": "production"},
    )
    context["error"]["file"] = "/repo/src/loader.py"

    issue = github_issue.build_issue(context, {"GITHUB": {"repo": "o/n"}})

    assert "```json" in issue["body"], "default no longer attaches the evidence"
    assert "APP_ENV" in issue["body"]
    assert github_issue.FINGERPRINT_MARKER in issue["body"]


# --- per-sink policy ---------------------------------------------------------

def test_a_section_set_to_zero_is_absent_not_empty():
    """A reader must be able to tell 'not collected' from 'collected, empty'."""
    context = {"error": {}, "variables": {"locals": {"a": "1"}}, "environment": {"X": "1"}}
    selected = evidence.select(
        context, {"EVIDENCE": {"provider": {"environment": 0}}}, "provider"
    )
    assert "environment" not in selected
    assert "variables" in selected


def test_logs_are_limited_by_LINES_not_characters():
    context = {"error": {}, "recent_logs": [f"line {i}" for i in range(100)]}
    selected = evidence.select(context, {"EVIDENCE": {"issue": {"logs": 5}}}, "issue")
    assert len(selected["recent_logs"]) == 5
    assert selected["recent_logs"][-1] == "line 99", "kept the oldest instead of the newest"


def test_every_variable_survives_and_is_trimmed_individually():
    """One huge value must not push the rest of the state out of the report."""
    context = {
        "error": {},
        "variables": {"locals": {
            "huge": {"value_preview": "H" * 10000},
            "small": {"value_preview": "ok"},
            "also_small": {"value_preview": "fine"},
        }},
    }
    selected = evidence.select(
        context, {"EVIDENCE": {"provider": {"variables": 50}}}, "provider"
    )
    locals_ = selected["variables"]["locals"]
    assert set(locals_) == {"huge", "small", "also_small"}, "a variable was dropped"
    assert len(locals_["huge"]["value_preview"]) < 100
    assert locals_["small"]["value_preview"] == "ok", "a short value was altered"


def test_essential_sections_are_never_negotiable():
    """Without the error and the source there is nothing to diagnose."""
    context = {
        "error": {"type": "KeyError"},
        "function_info": {"source_code": "def f(): ..."},
        "ai_hint": "hint",
        "variables": {"locals": {}},
    }
    selected = evidence.select(
        context,
        {"EVIDENCE": {"provider": {s: 0 for s in evidence.SECTIONS}}},
        "provider",
    )
    assert selected["error"] and selected["function_info"] and selected["ai_hint"]


def test_an_unknown_sink_keeps_its_defaults_rather_than_emptying():
    assert evidence.policy({"EVIDENCE": {"typo": {"variables": 1}}}, "disk") == (
        evidence.DEFAULT_EVIDENCE["disk"]
    )


def test_a_malformed_limit_is_ignored_not_fatal():
    limits = evidence.policy({"EVIDENCE": {"issue": {"variables": "lots"}}}, "issue")
    assert limits["variables"] == evidence.DEFAULT_EVIDENCE["issue"]["variables"]
