import json

from healing_agent import mutation_backend


def _context():
    return {
        "error": {"file": "example.py", "type": "ValueError"},
        "function_info": {"name": "broken", "source_code": "def broken(): pass"},
    }


def test_direct_backend_uses_existing_function_replacer(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mutation_backend,
        "function_replacer",
        lambda context, fixed_code: calls.append((context, fixed_code)) or True,
    )

    assert mutation_backend.apply_mutation(_context(), "def broken(): return 1", {}) is True
    assert calls == [(_context(), "def broken(): return 1")]


def test_command_backend_sends_repair_payload(monkeypatch):
    captured = {}

    def fake_run(argv, input, **_kwargs):
        captured["argv"] = argv
        captured["payload"] = json.loads(input)

        class Result:
            returncode = 0
            stdout = '{"ok": true}'
            stderr = ""

        return Result()

    monkeypatch.setattr(mutation_backend.subprocess, "run", fake_run)

    assert mutation_backend.apply_mutation(
        _context(),
        "def broken(): return 1",
        {"MUTATION_BACKEND": "command", "MUTATION_COMMAND": "safe-mutate --aether"},
    ) is True
    assert captured["argv"] == ["safe-mutate", "--aether"]
    assert captured["payload"]["protocol_version"] == "healing-agent-mutation-v1"
    assert captured["payload"]["source_file"] == "example.py"
    assert captured["payload"]["function_name"] == "broken"
    assert captured["payload"]["fixed_code"] == "def broken(): return 1"


def test_command_backend_rejects_failed_response(monkeypatch):
    def fake_run(*_args, **_kwargs):
        class Result:
            returncode = 0
            stdout = '{"ok": false, "rolled_back": true, "error": "hidden test failed"}'
            stderr = ""

        return Result()

    monkeypatch.setattr(mutation_backend.subprocess, "run", fake_run)

    assert mutation_backend.apply_mutation(
        _context(),
        "def broken(): return 1",
        {"MUTATION_BACKEND": "command", "MUTATION_COMMAND": "safe-mutate"},
    ) is False
