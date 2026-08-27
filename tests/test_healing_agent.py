import importlib

import pytest


healing_module = importlib.import_module("healing_agent.healing_agent")


def _config(max_attempts=3, auto_fix=True):
    return {
        "MAX_ATTEMPTS": max_attempts,
        "AUTO_FIX": auto_fix,
        "AUTO_SYSCHANGE": False,
        "BACKUP_ENABLED": False,
        "SAVE_EXCEPTIONS": False,
        "SAVE_AI_FIXES": False,
        "DEBUG": False,
    }


def test_failed_healing_reraises_original_exception(monkeypatch):
    original = ValueError("application failure")
    monkeypatch.setattr(
        healing_module, "load_config", lambda: (_config(auto_fix=False), None)
    )
    async def no_repair(*_args, **_kwargs):
        return False, None

    # _attempt_healing is a coroutine function: the healing session is written
    # once and shared by the sync and async wrappers, so stubs must be too.
    monkeypatch.setattr(healing_module, "_attempt_healing", no_repair)

    @healing_module.healing_agent
    def broken():
        raise original

    with pytest.raises(ValueError) as caught:
        broken()

    assert caught.value is original


def test_max_attempts_bounds_recursive_repair(monkeypatch):
    attempts = []
    holder = {}
    monkeypatch.setattr(
        healing_module, "load_config", lambda: (_config(max_attempts=3), None)
    )

    async def fake_attempt(*_args, **kwargs):
        attempts.append(kwargs.get("attempt_number", _args[5]))
        return True, holder["wrapped"]()

    monkeypatch.setattr(healing_module, "_attempt_healing", fake_attempt)

    @healing_module.healing_agent
    def always_fails():
        raise RuntimeError("still broken")

    holder["wrapped"] = always_fails

    with pytest.raises(RuntimeError, match="still broken"):
        always_fails()

    assert attempts == [1, 2, 3]


def test_attempt_budget_resets_for_new_top_level_call(monkeypatch):
    attempts = []
    monkeypatch.setattr(
        healing_module, "load_config", lambda: (_config(max_attempts=1), None)
    )
    async def record_failed_attempt(*_args, **_kwargs):
        attempts.append("attempt")
        return False, None

    monkeypatch.setattr(healing_module, "_attempt_healing", record_failed_attempt)

    @healing_module.healing_agent
    def broken():
        raise LookupError("broken")

    for _ in range(2):
        with pytest.raises(LookupError):
            broken()

    assert attempts == ["attempt", "attempt"]


def test_invalid_local_max_attempts_preserves_application_error(monkeypatch):
    monkeypatch.setattr(
        healing_module, "load_config", lambda: (_config(max_attempts=3), None)
    )

    @healing_module.healing_agent(MAX_ATTEMPTS=0)
    def broken():
        raise ArithmeticError("application failure")

    with pytest.raises(ArithmeticError, match="application failure") as caught:
        broken()

    assert isinstance(caught.value.__cause__, ValueError)


def test_a_same_length_candidate_is_not_served_from_stale_bytecode(tmp_path, monkeypatch):
    """A repaired module must run the repaired source, not a cached .pyc.

    Python treats a cached .pyc as valid when the source's mtime AND size match
    what it recorded - and mtime is stored with SECOND resolution. A candidate
    that happens to be the same byte length as the code it replaces, written
    within the same second, therefore reloaded the ORIGINAL bytecode: the file
    on disk was repaired while the process kept running the old code, which is
    indistinguishable from the repair silently not working.

    The candidate below is byte-for-byte the same length as what it replaces,
    which is how this was found - "missing" and "try_one" are both seven
    characters.
    """
    import importlib.util
    import sys

    original = (
        'import healing_agent\n'
        '\n'
        '@healing_agent\n'
        'def pick(v):\n'
        '    return v["aaaaaaa"]\n'
    )
    candidate = 'def pick(v):\n    return "healedxxxx"\n'

    path = tmp_path / "stale_reload.py"
    path.write_text(original, encoding="utf-8")
    size_before = path.stat().st_size

    monkeypatch.setattr(healing_module, "load_config", lambda: (_config(max_attempts=1), None))
    monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "hint")
    monkeypatch.setattr(healing_module, "fix", lambda *_a, **_k: candidate)

    # The initial import writes the bytecode cache for the ORIGINAL source.
    spec = importlib.util.spec_from_file_location("stale_reload", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["stale_reload"] = module
    spec.loader.exec_module(module)

    try:
        result = module.pick({})
    finally:
        sys.modules.pop("stale_reload", None)

    assert path.stat().st_size == size_before, (
        "the candidate must be the same size as the original for this test to "
        "exercise the cache at all"
    )
    assert result == "healedxxxx", (
        "the reload served stale bytecode: the file was repaired but the "
        "original code ran"
    )
