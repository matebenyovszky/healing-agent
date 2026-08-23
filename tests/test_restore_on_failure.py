"""
Restore-on-failure tests — no API key / network required.

A definitive healing failure must leave the source file byte-identical to its
pre-healing state. The generated candidate stays available separately.
"""

import importlib
import sys

import pytest

from healing_agent.code_backup import restore_backup

healing_module = importlib.import_module("healing_agent.healing_agent")


# --- restore_backup unit behavior -------------------------------------------

def test_restore_backup_reverts_a_mutated_file(tmp_path):
    original = tmp_path / "module.py"
    original.write_text("original\n", encoding="utf-8")
    backup = tmp_path / "module.bak.py"
    backup.write_text("original\n", encoding="utf-8")

    original.write_text("mutated\n", encoding="utf-8")

    assert restore_backup(str(backup), str(original)) is True
    assert original.read_text(encoding="utf-8") == "original\n"


def test_restore_backup_is_a_noop_when_file_is_unchanged(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("same\n", encoding="utf-8")
    backup = tmp_path / "module.bak.py"
    backup.write_text("same\n", encoding="utf-8")

    # Nothing was mutated, so nothing is restored and nothing is rewritten.
    assert restore_backup(str(backup), str(source)) is False
    assert source.read_text(encoding="utf-8") == "same\n"


def test_rapid_backups_do_not_collide(tmp_path):
    """Regression: a later attempt's backup must never overwrite the one
    holding the pre-healing source.

    Timestamps cannot carry this guarantee. Second precision obviously failed;
    microsecond precision failed too, intermittently, because `datetime.now()`
    has millisecond-or-worse granularity on Windows and two calls in quick
    succession return the identical value. Uniqueness now comes from an
    O_EXCL claim, so this test is deterministic rather than a coin flip.
    """
    from healing_agent.code_backup import create_backup

    source = tmp_path / "module.py"
    source.write_text("original\n", encoding="utf-8")
    context = {"error": {"file": str(source)}}

    paths = [create_backup(context)]
    for revision in range(9):
        source.write_text(f"mutated {revision}\n", encoding="utf-8")
        paths.append(create_backup(context))

    assert all(paths), "a backup failed outright"
    assert len(set(paths)) == len(paths), (
        f"backups collided: {len(paths) - len(set(paths))} name(s) reused"
    )
    with open(paths[0], encoding="utf-8") as handle:
        assert handle.read() == "original\n", (
            "the first backup no longer holds the pre-healing source"
        )


def test_a_failed_session_restores_the_original_not_a_later_mutation(tmp_path):
    """The collision above was not cosmetic: _register_backup keeps only the
    FIRST backup per file, so an overwritten first backup makes restore write
    the mutated code back instead of the original."""
    from healing_agent.code_backup import create_backup, restore_backup

    source = tmp_path / "module.py"
    source.write_text("original\n", encoding="utf-8")
    context = {"error": {"file": str(source)}}

    session_backup = create_backup(context)
    source.write_text("mutated\n", encoding="utf-8")
    create_backup(context)  # a second attempt, same instant

    assert restore_backup(session_backup, str(source)) is True
    assert source.read_text(encoding="utf-8") == "original\n"


def test_restore_backup_handles_missing_backup(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("kept\n", encoding="utf-8")

    assert restore_backup(str(tmp_path / "absent.py"), str(source)) is False
    assert source.read_text(encoding="utf-8") == "kept\n"


# --- full healing session ----------------------------------------------------

MODULE_SOURCE = '''
import healing_agent

@healing_agent
def broken(value):
    return value["missing"]
'''

# Syntactically valid, still wrong: healing must fail and be rolled back.
STILL_BROKEN_CANDIDATE = 'def broken(value):\n    return value["also_missing"]\n'


def _config(**overrides):
    config = {
        "MAX_ATTEMPTS": 1,
        "AUTO_FIX": True,
        "AUTO_SYSCHANGE": False,
        "BACKUP_ENABLED": True,
        "RESTORE_ON_FAILURE": True,
        "SAVE_EXCEPTIONS": False,
        "SAVE_AI_FIXES": False,
        "DEBUG": False,
        "GIT_MODE": "off",
    }
    config.update(overrides)
    return config


def _load_failing_module(tmp_path, monkeypatch, name, **config_overrides):
    """Write a broken module, stub the AI, and import it."""
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(MODULE_SOURCE, encoding="utf-8")

    monkeypatch.setattr(
        healing_module, "load_config", lambda: (_config(**config_overrides), None)
    )
    monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "stub hint")
    monkeypatch.setattr(healing_module, "fix", lambda *_a, **_k: STILL_BROKEN_CANDIDATE)

    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module_path, module


def test_failed_healing_restores_the_original_source(tmp_path, monkeypatch):
    module_path, module = _load_failing_module(
        tmp_path, monkeypatch, "restore_demo_failed"
    )
    before = module_path.read_bytes()

    with pytest.raises(Exception):
        module.broken({})

    assert module_path.read_bytes() == before, (
        "source file was left mutated after a failed healing session"
    )


def test_restore_can_be_disabled(tmp_path, monkeypatch):
    module_path, module = _load_failing_module(
        tmp_path,
        monkeypatch,
        "restore_demo_disabled",
        RESTORE_ON_FAILURE=False,
    )
    before = module_path.read_bytes()

    with pytest.raises(Exception):
        module.broken({})

    # Opt-out keeps the mutated file for inspection.
    assert module_path.read_bytes() != before
    assert "also_missing" in module_path.read_text(encoding="utf-8")


def test_restore_targets_the_pre_healing_source_across_nested_attempts(
    tmp_path, monkeypatch
):
    """With several attempts the file is mutated repeatedly; the restore must
    return the ORIGINAL source, not an intermediate healed revision."""
    candidates = iter(
        [
            'def broken(value):\n    return value["first_try"]\n',
            'def broken(value):\n    return value["second_try"]\n',
        ]
    )
    module_path = tmp_path / "restore_demo_nested.py"
    module_path.write_text(MODULE_SOURCE, encoding="utf-8")

    monkeypatch.setattr(
        healing_module, "load_config", lambda: (_config(MAX_ATTEMPTS=2), None)
    )
    monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "stub hint")
    monkeypatch.setattr(
        healing_module, "fix", lambda *_a, **_k: next(candidates, STILL_BROKEN_CANDIDATE)
    )

    spec = importlib.util.spec_from_file_location("restore_demo_nested", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["restore_demo_nested"] = module
    spec.loader.exec_module(module)
    before = module_path.read_bytes()

    with pytest.raises(Exception):
        module.broken({})

    restored = module_path.read_text(encoding="utf-8")
    assert module_path.read_bytes() == before
    assert "first_try" not in restored and "second_try" not in restored


def test_successful_healing_keeps_the_repaired_source(tmp_path, monkeypatch):
    """The restore must never undo a repair that actually worked."""
    module_path = tmp_path / "restore_demo_success.py"
    module_path.write_text(MODULE_SOURCE, encoding="utf-8")

    monkeypatch.setattr(healing_module, "load_config", lambda: (_config(), None))
    monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "stub hint")
    monkeypatch.setattr(
        healing_module,
        "fix",
        lambda *_a, **_k: 'def broken(value):\n    return value.get("missing", "healed")\n',
    )

    spec = importlib.util.spec_from_file_location("restore_demo_success", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["restore_demo_success"] = module
    spec.loader.exec_module(module)

    assert module.broken({}) == "healed"
    assert "healed" in module_path.read_text(encoding="utf-8")
