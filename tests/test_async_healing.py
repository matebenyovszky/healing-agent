"""Async functions must heal exactly like synchronous ones.

An `async def` returns its coroutine before its body runs, so a synchronous
wrapper's `try` never sees the exception: `await`ing the result raised outside
the decorator, and healing was silently skipped for every coroutine function.

The session itself is written once, as a coroutine, and shared by both
wrappers. These tests pin both halves of that arrangement: the async path
reaches the session, and the sync path still runs it without an event loop.

`asyncio.run` is used directly rather than adding a pytest async plugin — one
`run()` per test is less machinery than a new dev dependency.
"""

import asyncio
import importlib
import inspect

import pytest

healing_module = importlib.import_module("healing_agent.healing_agent")


def _config(**overrides):
    config = {
        "MAX_ATTEMPTS": 1,
        "DEBUG": False,
        "AUTO_FIX": False,
        "BACKUP_ENABLED": False,
        "SAVE_EXCEPTIONS": False,
        "SAVE_AI_FIXES": False,
        "RESTORE_ON_FAILURE": False,
    }
    config.update(overrides)
    return config


@pytest.fixture(autouse=True)
def _stub_config(monkeypatch):
    monkeypatch.setattr(healing_module, "load_config", lambda: (_config(), None))


def test_decorating_an_async_function_yields_a_coroutine_function():
    @healing_module.healing_agent
    async def sample():
        return "ok"

    assert inspect.iscoroutinefunction(sample)
    assert asyncio.run(sample()) == "ok"


def test_async_failure_reaches_the_healing_session(monkeypatch):
    # The regression: this counter stayed at zero because the exception was
    # raised at the caller's await, outside the decorator entirely.
    seen = []

    async def no_repair(*_args, **_kwargs):
        seen.append("attempted")
        return False, None

    monkeypatch.setattr(healing_module, "_attempt_healing", no_repair)
    original = ValueError("async application failure")

    @healing_module.healing_agent
    async def broken():
        raise original

    with pytest.raises(ValueError) as caught:
        asyncio.run(broken())

    assert seen == ["attempted"], "healing never ran for the coroutine function"
    assert caught.value is original, "the original exception must be the one raised"


def test_async_repair_result_is_returned(monkeypatch):
    async def repaired(*_args, **_kwargs):
        return True, "healed value"

    monkeypatch.setattr(healing_module, "_attempt_healing", repaired)

    @healing_module.healing_agent
    async def broken():
        raise RuntimeError("boom")

    assert asyncio.run(broken()) == "healed value"


def test_async_attempt_budget_is_honoured(monkeypatch):
    attempts = []
    monkeypatch.setattr(
        healing_module, "load_config", lambda: (_config(MAX_ATTEMPTS=3), None)
    )
    holder = {}

    async def fake_attempt(*_args, **kwargs):
        attempts.append(kwargs.get("attempt_number", _args[5]))
        return True, await holder["wrapped"]()

    monkeypatch.setattr(healing_module, "_attempt_healing", fake_attempt)

    @healing_module.healing_agent
    async def always_fails():
        raise RuntimeError("still broken")

    holder["wrapped"] = always_fails

    with pytest.raises(RuntimeError, match="still broken"):
        asyncio.run(always_fails())

    assert attempts == [1, 2, 3]


def test_sync_functions_are_unaffected(monkeypatch):
    async def repaired(*_args, **_kwargs):
        return True, 7

    monkeypatch.setattr(healing_module, "_attempt_healing", repaired)

    @healing_module.healing_agent
    def broken():
        raise RuntimeError("boom")

    assert not inspect.iscoroutinefunction(broken)
    assert broken() == 7


def test_run_sync_refuses_a_session_that_suspends():
    # The sync path drives the shared coroutine by hand, which is only valid
    # while it has no suspension points. If one is ever introduced, this must
    # fail loudly rather than hand the application an un-awaited coroutine.
    async def suspends():
        await asyncio.sleep(0)
        return "unreachable"

    with pytest.raises(RuntimeError, match="suspended in a synchronous context"):
        healing_module._run_sync(suspends())


def test_run_sync_propagates_the_session_exception():
    async def fails():
        raise KeyError("from inside the session")

    with pytest.raises(KeyError, match="from inside the session"):
        healing_module._run_sync(fails())


def test_invoke_awaits_only_what_is_awaitable():
    async def coroutine_target():
        return "awaited"

    def plain_target():
        return "direct"

    # A model can answer an `async def` with a plain `def`; awaiting that
    # unconditionally would turn a usable repair into "not awaitable".
    assert asyncio.run(healing_module._invoke(coroutine_target, (), {}, True)) == (
        "awaited"
    )
    assert asyncio.run(healing_module._invoke(plain_target, (), {}, True)) == "direct"
    assert asyncio.run(healing_module._invoke(plain_target, (), {}, False)) == "direct"
