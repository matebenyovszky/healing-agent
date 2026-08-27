"""Nothing captured may reach a destination without passing redaction.

The project makes one unconditional promise about evidence: a single chokepoint
sees everything before it is written to disk, sent to a provider, or attached
to a GitHub issue. That promise is only as good as the position of one call —
anything added to the context after `redact()` runs travels verbatim.

Two sections used to be added after it, and both are exactly the kind that
carries secrets: `healing_request["details"]` is arbitrary caller data (the
README's own example passes a row of business data), and log records are free
text where `logger.info(f"token={t}")` is ordinary.
"""

import importlib
import importlib.util
import json
import logging
import sys

import pytest

healing_module = importlib.import_module("healing_agent.healing_agent")
log_buffer = importlib.import_module("healing_agent.log_buffer")

# The secret is assembled at runtime on purpose. A literal in the module would
# also appear in `function_info["source_code"]`, which legitimately travels —
# a function cannot be repaired without its own source — and the test would
# then be measuring the wrong thing.
REQUESTING_MODULE = '''
import healing_agent

SECRET = "sk-live-" + "SHOULD-NOT-TRAVEL"

@healing_agent
def load(rows):
    healing_agent.request_healing(
        "rows do not satisfy the contract",
        details={"api_key": SECRET, "customer": "Alfa Kft"},
    )
'''

CRASHING_MODULE = '''
import healing_agent

@healing_agent
def load(rows):
    return rows[0]["amount"]
'''

SECRET_IN_A_LOG = "token=ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def _config(**overrides):
    config = {
        "MAX_ATTEMPTS": 1,
        "AUTO_FIX": False,
        "AUTO_SYSCHANGE": False,
        "BACKUP_ENABLED": False,
        "RESTORE_ON_FAILURE": False,
        "SAVE_EXCEPTIONS": False,
        "SAVE_AI_FIXES": False,
        "DEBUG": False,
        "GIT_MODE": "off",
        "REDACT_SECRETS": True,
    }
    config.update(overrides)
    return config


@pytest.fixture
def provider_payload(tmp_path, monkeypatch):
    """Run one healing attempt and hand back the context the fixer received."""
    seen = {}

    def run(source, name, **config_overrides):
        monkeypatch.setattr(
            healing_module,
            "load_config",
            lambda: (_config(**config_overrides), None),
        )
        monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "hint")

        def record(context, config):
            seen["context"] = context
            return None

        monkeypatch.setattr(healing_module, "fix", record)

        path = tmp_path / f"{name}.py"
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        try:
            with pytest.raises(Exception):
                module.load([{"other": 1}])
        finally:
            sys.modules.pop(name, None)
        return seen["context"]

    yield run


def test_request_details_are_redacted(provider_payload):
    context = provider_payload(REQUESTING_MODULE, "redaction_request")

    details = context["healing_request"]["details"]
    assert details["api_key"] != "sk-live-SHOULD-NOT-TRAVEL", (
        "caller-supplied details bypassed the redaction chokepoint"
    )
    assert "SHOULD-NOT-TRAVEL" not in json.dumps(context, default=str)
    # Redaction masks values, never structure: the repair still needs to know
    # which fields the caller was talking about.
    assert details["customer"] == "Alfa Kft"
    assert context["healing_request"]["reason"].startswith("rows do not satisfy")


def test_log_records_pass_through_the_chokepoint(provider_payload):
    log_buffer.enable_log_capture(size=10)
    application = logging.getLogger("the_application")
    application.setLevel(logging.INFO)
    application.info("calling the supplier with %s", SECRET_IN_A_LOG)
    try:
        context = provider_payload(
            CRASHING_MODULE, "redaction_logs", LOG_BUFFER_SIZE=10
        )
    finally:
        log_buffer.disable_log_capture()

    assert context.get("recent_logs"), "the log narrative was lost"
    blob = json.dumps(context, default=str)
    assert "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" not in blob, (
        "a token in a log record bypassed the redaction chokepoint"
    )
    assert "calling the supplier" in blob, "the narrative itself must survive"


def test_redaction_can_still_be_disabled(provider_payload):
    # The switch stays a switch: an operator who turned redaction off gets the
    # raw context, including the sections now covered by the chokepoint.
    context = provider_payload(
        REQUESTING_MODULE, "redaction_off", REDACT_SECRETS=False
    )

    assert (
        context["healing_request"]["details"]["api_key"]
        == "sk-live-SHOULD-NOT-TRAVEL"
    )
