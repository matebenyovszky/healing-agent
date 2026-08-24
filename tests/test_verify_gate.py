import json
import sys
import textwrap

import healing_agent.verify_gate as verify_gate
from healing_agent.verify_gate import _argv, verify_candidate


def _context(source):
    return {
        "error": {
            "file": str(source),
            "function_name": "broken",
            "line_number": 1,
            "error_line": "return 1",
        },
        "function_info": {"name": "broken", "starting_line_number": 1},
    }


def test_command_gate_runs_against_isolated_candidate(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text("def broken():\n    return 1\n", encoding="utf-8")
    probe = tmp_path / "probe.py"
    seen = tmp_path / "seen.json"
    probe.write_text(
        textwrap.dedent(
            f"""
            import json
            import os
            from pathlib import Path

            payload = json.loads(os.environ["HEALING_AGENT_CANDIDATE"])
            candidate = Path(payload["source_file"])
            assert candidate.exists()
            assert "return 2" in candidate.read_text(encoding="utf-8")
            assert Path(payload["original_file"]).read_text(encoding="utf-8").endswith("return 1\\n")
            Path({str(seen)!r}).write_text(json.dumps({{"ok": True}}), encoding="utf-8")
            print(json.dumps({{"ok": True}}))
            """
        ),
        encoding="utf-8",
    )

    assert verify_candidate(
        _context(source),
        "def broken():\n    return 2\n",
        {"VERIFY_COMMAND": [sys.executable, str(probe)]},
    )
    assert source.read_text(encoding="utf-8").endswith("return 1\n")
    assert json.loads(seen.read_text(encoding="utf-8")) == {"ok": True}


def test_command_gate_rejects_nonzero_exit_with_json_detail(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text("def broken():\n    return 1\n", encoding="utf-8")
    probe = tmp_path / "reject.py"
    probe.write_text(
        "import json, sys\nprint(json.dumps({'ok': False, 'error': 'nope'}))\nsys.exit(3)\n",
        encoding="utf-8",
    )

    assert not verify_candidate(
        _context(source),
        "def broken():\n    return 2\n",
        {"VERIFY_COMMAND": [sys.executable, str(probe)]},
    )
    assert source.read_text(encoding="utf-8").endswith("return 1\n")


def test_command_string_uses_windows_safe_split(monkeypatch):
    monkeypatch.setattr(verify_gate.os, "name", "nt")

    assert _argv('"C:\\Program Files\\Aether\\aether.exe" check') == [
        "C:\\Program Files\\Aether\\aether.exe",
        "check",
    ]


def test_unstartable_gate_is_a_configuration_error_not_a_rejection(tmp_path):
    """A gate that cannot start must not masquerade as a bad candidate.

    Silently returning False here would block every repair while looking like
    the model kept producing broken code — the operator would never learn that
    the command is simply misconfigured.
    """
    import pytest

    source = tmp_path / "demo.py"
    source.write_text("def broken():\n    return 1\n", encoding="utf-8")

    with pytest.raises(verify_gate.VerifyGateConfigurationError):
        verify_candidate(
            _context(source),
            "def broken():\n    return 2\n",
            {"VERIFY_COMMAND": ["definitely-not-an-executable-xyz"]},
        )

    # The live file is still untouched, as with any other gate outcome.
    assert source.read_text(encoding="utf-8").endswith("return 1\n")


def test_several_gates_run_in_order_and_stop_at_the_first_rejection(tmp_path):
    """Ordered gates are expressed as a list of argument lists."""
    source = tmp_path / "demo.py"
    source.write_text("def broken():\n    return 1\n", encoding="utf-8")
    marker = tmp_path / "second_ran.txt"

    reject = tmp_path / "reject.py"
    reject.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    second = tmp_path / "second.py"
    second.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )

    assert not verify_candidate(
        _context(source),
        "def broken():\n    return 2\n",
        {"VERIFY_COMMAND": [[sys.executable, str(reject)], [sys.executable, str(second)]]},
    )
    assert not marker.exists(), "a later gate ran after an earlier one rejected"
