"""
Observation tests: explicit capture and the optional log ring buffer.

No API key or network required. Observation must never raise into the program
it observes, and the ring buffer must be genuinely off when not configured.
"""

import importlib
import json
import logging

import pytest

capture_module = importlib.import_module("healing_agent.capture")
log_buffer = importlib.import_module("healing_agent.log_buffer")
healing_module = importlib.import_module("healing_agent.healing_agent")
fixer = importlib.import_module("healing_agent.ai_code_fixer")
hinter = importlib.import_module("healing_agent.ai_hint_generator")


@pytest.fixture(autouse=True)
def _clean_buffer():
    """Never leak an armed handler between tests."""
    log_buffer.disable_log_capture()
    yield
    log_buffer.disable_log_capture()


# --- capture() ---------------------------------------------------------------

def test_capture_writes_a_redacted_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(
        capture_module,
        "load_config",
        lambda: ({"REDACT_SECRETS": True, "CAPTURE_DIR": str(tmp_path)}, None),
        raising=False,
    )

    # Deliberately unused: the point is that a local named `password` is
    # captured and redacted by NAME, which requires it to exist and nothing
    # more. Hence the noqa - the lint rule is right in general, wrong here.
    password = "hunter2"          # noqa: F841 - must be redacted by name
    order_count = 7               # must survive
    path = capture_module.capture("supplier response", CAPTURE_DIR=str(tmp_path))

    assert path is not None
    payload = json.loads(open(path, encoding="utf-8").read())
    assert payload["capture_label"] == "supplier response"
    assert payload["capture_type"] == "debug"
    assert payload["source"]["function"] == "test_capture_writes_a_redacted_snapshot"

    locals_ = payload["variables"]["locals"]
    assert locals_["password"] == "<redacted>", "capture leaked a secret-named local"
    assert "7" in locals_["order_count"]["value_preview"]
    assert order_count == 7  # keep the local alive for the capture above


def test_capture_snapshots_the_callers_frame(tmp_path):
    """The snapshot must describe the caller, not capture()'s own internals."""
    marker_value = "caller-frame-marker"
    path = capture_module.capture("frame check", CAPTURE_DIR=str(tmp_path))
    payload = json.loads(open(path, encoding="utf-8").read())
    previews = [
        entry.get("value_preview", "")
        for entry in payload["variables"]["locals"].values()
        if isinstance(entry, dict)
    ]
    assert any(marker_value in preview for preview in previews)


def test_capture_never_raises(monkeypatch):
    """Observation must not break the observed program."""
    def explode(*_args, **_kwargs):
        raise RuntimeError("capture internals failed")

    monkeypatch.setattr(capture_module, "capture_context", explode)
    assert capture_module.capture("boom") is None


def test_capture_filename_is_sanitised(tmp_path):
    path = capture_module.capture("weird/label: with*chars", CAPTURE_DIR=str(tmp_path))
    assert path is not None
    assert "/" not in path.rsplit("\\", 1)[-1].replace("\\", "")


# --- ring buffer -------------------------------------------------------------

def test_buffer_is_off_by_default():
    assert log_buffer.recent_records() is None
    assert log_buffer.enable_log_capture(size=0) == 0
    assert log_buffer.recent_records() is None


def test_missing_or_zero_config_does_not_install_a_handler():
    for value in (0, None, "", "0"):
        assert log_buffer.enable_log_capture(config={"LOG_BUFFER_SIZE": value}) == 0
        assert log_buffer.recent_records() is None


def test_positive_size_records_recent_lines():
    assert log_buffer.enable_log_capture(size=3) == 3
    logger = logging.getLogger("demo.app")
    for index in range(5):
        logger.warning("processing page %s", index)

    records = log_buffer.recent_records()
    assert records is not None and len(records) == 3, records
    assert "processing page 4" in records[-1]
    assert "processing page 0" not in "\n".join(records), "buffer did not roll over"


def test_config_size_can_lower_what_is_sent():
    log_buffer.enable_log_capture(size=10)
    logger = logging.getLogger("demo.app")
    for index in range(10):
        logger.warning("line %s", index)

    assert len(log_buffer.recent_records({"LOG_BUFFER_SIZE": 2})) == 2


def test_long_records_are_capped():
    log_buffer.enable_log_capture(size=2)
    logging.getLogger("demo.app").warning("x" * 5000)
    assert len(log_buffer.recent_records()[0]) <= log_buffer.MAX_RECORD_CHARS + 2


def test_handler_never_raises_on_an_unformattable_record():
    """Our handler must swallow formatting errors. Exercised directly: routing
    through logging would hit pytest's own capture handler first, which raises
    on an unformattable record before ours is reached."""

    class Unprintable:
        def __str__(self):
            raise ValueError("cannot render")

    handler = log_buffer.RingBufferHandler(size=2)
    record = logging.LogRecord(
        name="demo.app",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="value=%s",
        args=(Unprintable(),),
        exc_info=None,
    )
    handler.emit(record)  # must not raise
    assert list(handler.records) == [], "an unformattable record was stored"


def test_disable_removes_the_handler():
    log_buffer.enable_log_capture(size=2)
    logging.getLogger("demo.app").warning("recorded")
    assert log_buffer.recent_records()
    log_buffer.disable_log_capture()
    assert log_buffer.recent_records() is None


# --- prompt wiring -----------------------------------------------------------

def _context(**extra):
    context = {
        "function_info": {
            "name": "load_sales",
            "source_code": "def load_sales(): ...",
            "signature": "()",
            "module": "demo",
        },
        "function_arguments": {
            "payload": {"value": "{'datum': '2026-01-01'}", "type": "dict"}
        },
        "error": {
            "type": "KeyError",
            "message": "'amount'",
            "line_number": 3,
            "error_line": "row['amount']",
            "exception_attrs": {},
            "traceback_frames": [],
            "traceback": "Traceback...",
            "function_name": "load_sales",
        },
    }
    context.update(extra)
    return context


def test_logs_reach_the_fix_prompt_only_when_present():
    without = fixer.prepare_fix_prompt(_context())
    assert "log records leading up to" not in without

    with_logs = fixer.prepare_fix_prompt(
        _context(recent_logs=["10:00 INFO app: fetching supplier feed v2"])
    )
    assert "fetching supplier feed v2" in with_logs


def test_arguments_are_rendered_without_the_capture_wrapper(monkeypatch):
    """The model must not read the {value, type} wrapper as the argument's own
    keys, which produced a misleading hint in a live run."""
    captured = {}
    monkeypatch.setattr(
        hinter, "get_ai_response", lambda prompt, *_a, **_k: captured.setdefault("p", prompt)
    )
    hinter.generate_hint(_context(), {})
    prompt = captured["p"]
    assert "payload (type: dict) = {'datum': '2026-01-01'}" in prompt
    assert "'value':" not in prompt, "raw capture wrapper leaked into the prompt"
