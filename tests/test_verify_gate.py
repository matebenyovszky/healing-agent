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
