"""Every destination is governed by the evidence policy, with no exceptions.

`EVIDENCE` is only a policy if it applies everywhere the context goes. Two
readers used to sit outside it: the hint call — the FIRST of the two provider
calls a repair makes — and the verification gate, which handed a subprocess the
whole context through an environment variable.
"""

import importlib
import json

import pytest

hint_generator = importlib.import_module("healing_agent.ai_hint_generator")
ai_code_fixer = importlib.import_module("healing_agent.ai_code_fixer")
verify_gate = importlib.import_module("healing_agent.verify_gate")

BIG = "x" * 3000


def _context():
    return {
        "python_version": "3.13",
        "platform": "win32",
        "error": {
            "type": "KeyError",
            "message": "'amount'",
            "function_name": "load",
            "traceback": "Traceback…",
            "traceback_frames": [],
            "exception_attrs": {},
            "file": "loader.py",
            "line_number": 2,
            "error_line": "row['amount']",
        },
        "function_info": {
            "name": "load",
            "qualname": "load",
            "module": "loader",
            "source_code": "def load(rows):\n    return rows[0]['amount']",
        },
        "function_arguments": {"rows": {"value": BIG, "type": "list"}},
        "variables": {"locals": {"total": {"type": "str", "value_preview": BIG}}},
        "environment": {"APP_ENV": "production"},
        "recent_logs": [f"line {i}" for i in range(80)],
    }


LEAN = {
    "EVIDENCE": {
        "provider": {"arguments": 0, "variables": 0, "environment": 0, "logs": 0}
    }
}


def _prompt(module, config, monkeypatch, context=None):
    captured = {}

    def record(prompt, _config, system_role=None):
        captured["prompt"] = prompt
        return "def load(rows):\n    return 1\n"

    monkeypatch.setattr(module, "get_ai_response", record)
    if module is hint_generator:
        module.generate_hint(context or _context(), config)
    else:
        module.fix(context or _context(), config)
    return captured["prompt"]


def test_the_hint_call_honours_the_provider_policy(monkeypatch):
    default = _prompt(hint_generator, {}, monkeypatch)
    lean = _prompt(hint_generator, LEAN, monkeypatch)

    assert len(lean) < len(default), (
        "EVIDENCE had no effect on the hint prompt, the first of the two "
        "provider calls a repair makes"
    )
    assert BIG not in lean, "arguments were sent despite arguments: 0"
    assert "line 79" not in lean, "log records were sent despite logs: 0"


def test_the_fix_call_still_honours_the_provider_policy(monkeypatch):
    default = _prompt(ai_code_fixer, {}, monkeypatch)
    lean = _prompt(ai_code_fixer, LEAN, monkeypatch)

    assert len(lean) < len(default)
    assert BIG not in lean


def test_both_provider_calls_keep_what_is_never_negotiable(monkeypatch):
    for module in (hint_generator, ai_code_fixer):
        prompt = _prompt(module, LEAN, monkeypatch)
        assert "def load(rows):" in prompt, "the source is required to repair"
        assert "KeyError" in prompt, "the error is required to diagnose"


def test_the_stated_reason_reaches_the_hint(monkeypatch):
    # The hint is fed to the fix prompt as "AI Analysis". A hint written
    # without the stated reason makes the repair reason about a crash that
    # never happened.
    context = _context()
    context["healing_request"] = {
        "reason": "the amount column was renamed",
        "details": {"headers_seen": ["osszeg"]},
    }

    prompt = _prompt(hint_generator, {}, monkeypatch, context)

    assert "the amount column was renamed" in prompt
    assert "did not crash" in prompt
    assert "osszeg" in prompt


def test_the_verify_gate_carries_the_disk_selection(tmp_path, monkeypatch):
    source = tmp_path / "loader.py"
    source.write_text("def load(rows):\n    return rows[0]['amount']\n", encoding="utf-8")

    context = _context()
    context["error"]["file"] = str(source)
    context["function_info"]["starting_line_number"] = 1

    seen = {}

    def fake_run(argv, **kwargs):
        seen["candidate"] = json.loads(kwargs["env"]["HEALING_AGENT_CANDIDATE"])

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(verify_gate.subprocess, "run", fake_run)

    config = {
        "VERIFY_COMMAND": ["true"],
        "EVIDENCE": {"disk": {"arguments": 0, "variables": 0,
                              "environment": 0, "logs": 5}},
    }
    assert verify_gate.verify_candidate(
        context, "def load(rows):\n    return 1\n", config
    )

    handed_over = seen["candidate"]["context"]
    assert "function_arguments" not in handed_over, (
        "the gate received the full context, outside the evidence policy"
    )
    assert "variables" not in handed_over
    assert len(handed_over["recent_logs"]) == 5
    # The gate cannot judge a candidate it cannot see.
    assert handed_over["error"]["type"] == "KeyError"
    assert handed_over["fixed_code"].startswith("def load")


@pytest.mark.parametrize("sink", ["disk", "provider", "issue"])
def test_a_sink_the_configuration_omits_keeps_its_defaults(sink):
    from healing_agent.evidence import DEFAULT_EVIDENCE, policy

    assert policy({"EVIDENCE": {}}, sink) == DEFAULT_EVIDENCE[sink]
