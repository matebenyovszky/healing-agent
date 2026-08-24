"""Healing Agent's output inherits the host application's logging.

Records go to the standard logger `healing_agent`, which the library never
configures, so the application's level, handlers, formatters and filters apply
through the normal hierarchy. When the application configured nothing, the
console narration this project is used for must survive unchanged.
"""

import importlib
import logging

import pytest

console = importlib.import_module("healing_agent.console")
log_buffer = importlib.import_module("healing_agent.log_buffer")


@pytest.fixture(autouse=True)
def ha_logger(monkeypatch):
    """An unregistered stand-in for the library's logger.

    `logging.getLogger("healing_agent")` cannot be used here: pytest's logging
    plugin attaches its own capture handlers to the loggers in the manager
    registry — including ours — so the "application configured nothing" world
    is unreachable through it, and every console assertion would fail against
    the test runner's instrumentation rather than the library's behavior.

    `logging.Logger(...)` builds an instance the registry never sees. It starts
    with no handlers and no propagation, which is exactly the unconfigured
    world; tests that want a configured application opt in by adding a handler
    or attaching it to the root logger.
    """
    logger = logging.Logger(console.LOGGER_NAME)
    logger.propagate = False
    monkeypatch.setattr(console, "_logger", logger)
    previous_mode = console.get_output_mode()
    console.set_output_mode("auto")

    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        yield logger
    finally:
        log_buffer.disable_log_capture()
        root.handlers, root.level = saved_handlers, saved_level
        console.set_output_mode(previous_mode)


def _inherit_from_root(logger):
    """Put the stand-in where a real `healing_agent` logger sits."""
    logger.parent = logging.getLogger()
    logger.propagate = True


class Collector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_unconfigured_application_still_gets_the_console(capsys):
    console.emit("♣ narration")

    assert "♣ narration" in capsys.readouterr().out


def test_a_handler_on_our_logger_takes_over(capsys, ha_logger):
    collector = Collector()
    ha_logger.addHandler(collector)

    console.emit("♣ narration")

    assert capsys.readouterr().out == "", "output was duplicated to the console"
    assert [record.getMessage() for record in collector.records] == ["narration"]


def test_a_root_handler_is_inherited_through_propagation(capsys, ha_logger):
    collector = Collector()
    root = logging.getLogger()
    root.addHandler(collector)
    root.setLevel(logging.INFO)  # an application that asked to see INFO
    _inherit_from_root(ha_logger)

    console.emit("♣ narration")

    assert capsys.readouterr().out == ""
    assert "narration" in [record.getMessage() for record in collector.records]


def test_the_application_level_filters_our_records(ha_logger):
    collector = Collector()
    root = logging.getLogger()
    root.handlers = [collector]
    root.setLevel(logging.WARNING)
    _inherit_from_root(ha_logger)

    console.emit("♣ routine narration")
    console.emit("♣ something failed", level=logging.ERROR)

    # Inheriting the application's configuration means honouring it: an app
    # that asked for WARNING and above does not get INFO narration.
    assert [record.getMessage() for record in collector.records] == ["something failed"]


def test_levels_reach_the_handler(ha_logger):
    collector = Collector()
    ha_logger.addHandler(collector)

    console.emit("♣ info")
    console.emit("⚠ Warning: careful", level=logging.WARNING)
    console.emit("♣ broken", level=logging.ERROR)

    assert [record.levelno for record in collector.records] == [
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
    ]


def test_decoration_is_stripped_for_the_logger_only(capsys, ha_logger):
    collector = Collector()
    ha_logger.addHandler(collector)
    console.emit("⚠ Warning: careful", level=logging.WARNING)
    assert collector.records[0].getMessage() == "Warning: careful"

    ha_logger.handlers = []
    console.emit("⚠ Warning: careful", level=logging.WARNING)
    assert "⚠ Warning: careful" in capsys.readouterr().out


def test_print_mode_ignores_the_application_configuration(capsys, ha_logger):
    ha_logger.addHandler(Collector())
    console.set_output_mode("print")

    console.emit("♣ narration")

    assert "♣ narration" in capsys.readouterr().out


def test_logging_mode_never_prints(capsys):
    console.set_output_mode("logging")

    console.emit("♣ narration")

    assert capsys.readouterr().out == ""


def test_unknown_mode_falls_back_to_auto():
    console.set_output_mode("nonsense")
    assert console.get_output_mode() == "auto"


def test_the_log_ring_buffer_does_not_look_like_app_configuration(capsys, ha_logger):
    # log_buffer attaches to the ROOT logger. Treating that as "the application
    # configured logging" would silence the console the moment log capture is
    # armed, which is a surprising side effect of an unrelated feature.
    ha_logger.addHandler(log_buffer.RingBufferHandler(size=5))

    assert console._application_configured_logging() is False
    console.emit("♣ narration")

    assert "♣ narration" in capsys.readouterr().out


def test_our_own_narration_never_enters_the_evidence_buffer(ha_logger):
    log_buffer.enable_log_capture(size=5)
    console.set_output_mode("logging")
    _inherit_from_root(ha_logger)

    console.emit("♣ agent narration")
    assert log_buffer.recent_records() is None, (
        "the agent's own output was fed back into the context sent to the model"
    )

    application = logging.getLogger("the_application")
    application.setLevel(logging.INFO)  # the root logger defaults to WARNING
    application.info("supplier returned 12 rows")
    records = log_buffer.recent_records()
    assert records and any("supplier returned 12 rows" in line for line in records)


def test_a_broken_handler_never_reaches_the_application(ha_logger):
    class Exploding(logging.Handler):
        def emit(self, record):
            raise OSError("handler is broken")

    ha_logger.addHandler(Exploding())

    # Reporting must never become the application's failure; `logging` absorbs
    # handler errors itself, so nothing propagates out of this call.
    console.emit("♣ narration")

