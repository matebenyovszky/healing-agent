"""
What was tried, and why each attempt failed.

The escalated issue used to show a candidate with no sign that it had been
rejected, no reason, and no trace of later attempts — so a reader would take a
known-bad direction for the repair. These tests pin the record that fixes that.
"""

import importlib
import sys

import pytest

ledger = importlib.import_module("healing_agent.attempt_ledger")
healing_module = importlib.import_module("healing_agent.healing_agent")
github_issue = importlib.import_module("healing_agent.github_issue")
verify_gate = importlib.import_module("healing_agent.verify_gate")


# --- rendering ---------------------------------------------------------------

def test_nothing_is_rendered_without_attempts():
    assert ledger.render(None) == []
    assert ledger.render([]) == []


def test_each_attempt_shows_its_verdict_and_detail():
    lines = "\n".join(ledger.render([
        ledger.entry(1, "gate_rejected", "def f(): pass", "pytest exited 1: expected 2000, got 0"),
        ledger.entry(2, "still_failed", "def f(): raise", "KeyError: 'amount'"),
    ]))
    assert "Attempt 1" in lines and "rejected by a verify gate" in lines
    assert "expected 2000, got 0" in lines, "the verdict is the useful half"
    assert "Attempt 2" in lines and "applied, but the function still failed" in lines
    assert "KeyError: 'amount'" in lines


def test_a_reader_is_told_the_candidates_are_known_bad():
    """The whole point: a rejected candidate must not read as the repair."""
    rejected = ledger.render([ledger.entry(1, "gate_rejected", "def f(): pass")])
    assert any("known to fail" in line for line in rejected)

    accepted = ledger.render([ledger.entry(1, "healed", "def f(): pass")])
    assert not any("known to fail" in line for line in accepted)


def test_a_long_candidate_is_truncated_not_dropped():
    lines = "\n".join(ledger.render([ledger.entry(1, "gate_rejected", "x = 1\n" * 5000)]))
    assert "truncated" in lines
    assert "_healing_agent_fixes/" in lines, "the reader needs the full copy's location"
    assert len(lines) < 4000


# --- the gate reports its verdict -------------------------------------------

def test_the_gate_reports_why_it_rejected(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text("def broken():\n    return 1\n", encoding="utf-8")
    reject = tmp_path / "reject.py"
    reject.write_text(
        "import sys\nprint('expected 2000, got 0')\nsys.exit(3)\n", encoding="utf-8"
    )
    context = {
        "error": {"file": str(source), "function_name": "broken", "line_number": 1,
                  "error_line": "return 1"},
        "function_info": {"name": "broken", "starting_line_number": 1},
    }

    report = {}
    passed = verify_gate.verify_candidate(
        context, "def broken():\n    return 2\n",
        {"VERIFY_COMMAND": [sys.executable, str(reject)]}, report,
    )

    assert passed is False
    assert "exited 3" in report["reason"]
    assert "expected 2000, got 0" in report["reason"], (
        "the gate's own output is what tells a reader where to look"
    )


# --- the full session -------------------------------------------------------

MODULE = '''
import healing_agent

@healing_agent
def broken(v):
    return v["missing"]
'''


def _run_failing_session(tmp_path, monkeypatch, name, candidates, **config):
    escalated = {}
    monkeypatch.setattr(
        healing_module,
        "open_issue_for_failure",
        lambda context, cfg: escalated.setdefault("context", context),
    )
    base = {
        "MAX_ATTEMPTS": 2, "AUTO_FIX": True, "AUTO_SYSCHANGE": False,
        "BACKUP_ENABLED": True, "RESTORE_ON_FAILURE": True,
        "SAVE_EXCEPTIONS": False, "SAVE_AI_FIXES": False, "DEBUG": False,
        "GIT_MODE": "off", "GITHUB": {"issue_on_failure": True, "repo": "o/n"},
    }
    base.update(config)
    monkeypatch.setattr(healing_module, "load_config", lambda: (base, None))
    monkeypatch.setattr(healing_module, "generate_hint", lambda *a, **k: "hint")
    supply = iter(candidates)
    monkeypatch.setattr(healing_module, "fix", lambda *a, **k: next(supply, None))

    path = tmp_path / f"{name}.py"
    path.write_text(MODULE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

    with pytest.raises(Exception):
        module.broken({})
    return escalated.get("context", {})


def test_every_attempt_reaches_the_escalation(tmp_path, monkeypatch):
    context = _run_failing_session(
        tmp_path, monkeypatch, "ledger_all",
        ['def broken(v):\n    return v["try_one"]\n',
         'def broken(v):\n    return v["try_two"]\n'],
    )

    attempts = context.get("attempts")
    assert attempts and len(attempts) == 2, f"expected both attempts, got {attempts}"
    assert [a["attempt"] for a in attempts] == [1, 2]
    assert all(a["outcome"] == "still_failed" for a in attempts)
    # The later candidate used to be lost entirely.
    assert "try_two" in attempts[1]["candidate"]
    # And each carries the error the candidate actually produced.
    assert "try_one" in attempts[0]["detail"]


def test_no_candidate_is_recorded_as_such(tmp_path, monkeypatch):
    context = _run_failing_session(tmp_path, monkeypatch, "ledger_none", [None])
    attempts = context.get("attempts")
    assert attempts and attempts[0]["outcome"] == "no_candidate"
    assert attempts[0]["candidate"] is None


def test_a_free_text_detail_is_scrubbed(tmp_path, monkeypatch):
    """A gate's stderr is free text; name-based redaction cannot see inside it."""
    context = _run_failing_session(
        tmp_path, monkeypatch, "ledger_scrub",
        ['def broken(v):\n    raise RuntimeError("token sk-live-abcdefghijklmnop")\n'],
    )
    details = [a["detail"] for a in context["attempts"] if a.get("detail")]
    assert details, f"no attempt carried a detail: {context['attempts']}"
    joined = " ".join(details)
    assert "sk-live-abcdefghijklmnop" not in joined, joined
    assert "RuntimeError" in joined, "scrubbing must not destroy the diagnosis"


def test_the_issue_body_carries_the_attempts():
    issue = github_issue.build_issue(
        {
            "error": {"type": "KeyError", "message": "'amount'", "file": "/r/loader.py",
                      "line_number": 3, "error_line": "row['amount']"},
            "function_info": {"name": "load"},
            "attempts": [ledger.entry(1, "gate_rejected", "def load(): pass", "pytest exited 1")],
        },
        {"GITHUB": {"repo": "o/n", "issue_detail": "reference"}},
    )
    assert "### Repair attempts" in issue["body"]
    assert "pytest exited 1" in issue["body"]
    assert "known to fail" in issue["body"]


def test_entries_are_read_in_attempt_order_not_completion_order():
    """Attempts nest, so attempt 2 records BEFORE attempt 1 finishes.

    Rendered as recorded, the ledger reads backwards and inverts the narrative
    it exists to convey.
    """
    recorded = [ledger.entry(2, "no_candidate"), ledger.entry(1, "still_failed", "x = 1")]
    assert [r["attempt"] for r in ledger.ordered(recorded)] == [1, 2]

    lines = chr(10).join(ledger.render(recorded))
    assert lines.index("Attempt 1") < lines.index("Attempt 2")
