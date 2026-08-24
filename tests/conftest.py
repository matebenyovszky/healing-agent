"""Shared test setup.

Healing Agent's output goes to the application's logging when the application
configured any, and to the console when it did not. pytest's logging plugin
attaches capture handlers to the loggers in the registry — ours included — so
under the test runner the library always sees a "configured application" and
routes everything to the logger.

That is correct behavior reacting to a real handler, but it is the test
runner's instrumentation rather than the code under test, and it would silence
every assertion about console output. The suite therefore pins the console
explicitly. Tests that exercise the logging path (`test_console_logging.py`)
override this per test with their own logger.
"""

import importlib

import pytest

console = importlib.import_module("healing_agent.console")


@pytest.fixture(autouse=True)
def _pin_console_output():
    # Per test, not per session: `load_config()` applies the LOG_MODE from the
    # config file, so any test that loads a configuration would otherwise leak
    # that mode into every test after it.
    console.set_output_mode("print")
    yield
    console.set_output_mode("auto")
