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

def test_environment_keeps_names_but_masks_secrets(monkeypatch):
    monkeypatch.setenv("EV_DB_URL", "postgres://app:S3cr3t@db/prod")
    monkeypatch.setenv("EV_API_KEY", "totally-secret")
    monkeypatch.setenv("EV_REGION", "eu-central-1")

    environment = handler.capture_environment({})

    # Names are diagnostic in themselves — that a credential is SET matters.
    assert "EV_API_KEY" in environment
    assert environment["EV_API_KEY"] == redactor.DEFAULT_PLACEHOLDER
    assert "S3cr3t" not in environment["EV_DB_URL"]
    assert "db/prod" in environment["EV_DB_URL"], "over-redacted the host"
    assert environment["EV_REGION"] == "eu-central-1"


def test_environment_capture_can_be_switched_off():
    context = handler.capture_context(config={"CAPTURE_ENVIRONMENT": False})
    assert "environment" not in context


def test_environment_is_present_by_default():
    context = handler.capture_context(config={})
    assert context["environment"], "environment missing from a default capture"


# --- size policy: rich on disk, affordable on the way out --------------------

def test_capture_keeps_more_than_a_prompt_sends():
    assert handler.DEFAULT_VALUE_CHARS > handler.DEFAULT_PROMPT_VALUE_CHARS


def test_trim_values_shortens_strings_at_every_depth():
    trimmed = handler.trim_values(
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
