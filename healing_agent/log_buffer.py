"""
Optional ring buffer of the application's own log records.

A stack trace says WHERE a program broke. The log lines leading up to it say
WHAT it was doing — "fetching supplier CSV v2 endpoint", "retrying after 429",
"switched to fallback host". That narrative is exactly what a repair proposal
and an escalated issue are missing today.

Off by default. `LOG_BUFFER_SIZE = 0` (or absent) means the handler is never
installed, nothing is recorded, and no tokens are spent. A positive value is
the number of most recent records kept, and those records are included in the
captured context and sent to the model.

A buffer can only contain what was recorded BEFORE the failure, so it has to
be armed while the program is still healthy:

    import healing_agent
    healing_agent.enable_log_capture()        # size from LOG_BUFFER_SIZE
    healing_agent.enable_log_capture(50)      # or explicitly

⚠ Log messages are free text, so the name-based redaction that protects the
rest of the context has no field name to judge. Buffered lines are therefore
value-scrubbed on the way out (`redactor.scrub_value`), which masks URL
credentials and recognisable token shapes — but that is a denylist, and a
bespoke secret format will pass. Enable this only for loggers whose messages
you trust, and prefer a higher `LOG_BUFFER_LEVEL`.
"""

import logging
from collections import deque
from typing import Any, Dict, List, Optional

from .console import LOGGER_NAME, emit
from .redactor import DEFAULT_PLACEHOLDER, scrub_value

# Keep single records from dominating the prompt.
MAX_RECORD_CHARS = 300

_handler: Optional["RingBufferHandler"] = None


class RingBufferHandler(logging.Handler):
    """Keeps the most recent formatted log records in memory."""

    # Marks this handler as Healing Agent's own, so console.py does not mistake
    # it for the application having configured logging.
    _healing_agent_internal = True

    def __init__(self, size: int, level: int = logging.INFO):
        super().__init__(level=level)
        self.records: deque = deque(maxlen=size)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:  # noqa: A003 - logging API
        # The buffer is evidence about the APPLICATION. Healing Agent's own
        # narration would otherwise be fed back into the context sent to the
        # model, crowding out the lines that actually explain the failure.
        if record.name == LOGGER_NAME or record.name.startswith(LOGGER_NAME + "."):
            return
        try:
            line = self.format(record)
            if len(line) > MAX_RECORD_CHARS:
                line = line[:MAX_RECORD_CHARS] + " …"
            self.records.append(line)
        except Exception:
            # A logging handler must never raise into the application.
            pass


def enable_log_capture(
    size: Optional[int] = None,
    level: int = logging.INFO,
    config: Optional[Dict[str, Any]] = None,
) -> int:
    """Arm the ring buffer on the root logger. Returns the active size.

    Args:
        size: Number of records to keep. When omitted, `LOG_BUFFER_SIZE` from
            the configuration is used; 0 or missing means "do not install".
        level: Minimum level to record.
        config: Pre-loaded configuration, to avoid a second config read.
    """
    global _handler

    if size is None:
        if config is None:
            try:
                from .config_loader import load_config

                config, _ = load_config()
            except Exception:
                config = {}
        size = config.get("LOG_BUFFER_SIZE", 0) or 0
        level = _resolve_level(config.get("LOG_BUFFER_LEVEL"), level)

    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 0

    if size <= 0:
        disable_log_capture()
        return 0

    disable_log_capture()
    _handler = RingBufferHandler(size=size, level=level)
    logging.getLogger().addHandler(_handler)
    return size


def disable_log_capture() -> None:
    """Remove the ring buffer handler, if installed."""
    global _handler
    if _handler is not None:
        try:
            logging.getLogger().removeHandler(_handler)
        except Exception:
            pass
        _handler = None


def _resolve_level(configured: Any, default: int) -> int:
    if configured is None:
        return default
    if isinstance(configured, int):
        return configured
    resolved = logging.getLevelName(str(configured).upper())
    return resolved if isinstance(resolved, int) else default


def recent_records(config: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
    """Return the buffered log lines, or None when capture is not armed.

    The configured size is honored even if the buffer was armed with a larger
    one, so lowering `LOG_BUFFER_SIZE` immediately lowers what is sent.

    Value scrubbing is applied here rather than left to the name-based
    redaction that covers the rest of the context. A log line is free text with
    no field name to judge — `logger.info(f"token={t}")` is ordinary code — so
    the only filter that can see into it is the one that recognises the shape
    of a secret. This is the single place both the healing path and `capture()`
    read the buffer, so scrubbing here covers both.
    """
    if _handler is None:
        return None
    records = list(_handler.records)
    if not records:
        return None
    placeholder = (config or {}).get("REDACT_PLACEHOLDER") or DEFAULT_PLACEHOLDER
    if (config or {}).get("REDACT_SECRETS", True) is not False:
        records = [scrub_value(line, placeholder) for line in records]
    if config:
        try:
            limit = int(config.get("LOG_BUFFER_SIZE", 0) or 0)
        except (TypeError, ValueError):
            limit = 0
        if limit > 0:
            records = records[-limit:]
    return records


def buffered_log_text(config: Optional[Dict[str, Any]] = None) -> str:
    """Render the buffered records for a prompt, or an empty string."""
    records = recent_records(config)
    if not records:
        return ""
    return "\n".join(records)


def arm_from_config_if_requested(config: Dict[str, Any]) -> None:
    """Install the buffer late if configured but not yet armed.

    Late arming cannot recover the lines that led to the CURRENT failure, but
    it means a long-running process gets the narrative from the next one
    without an explicit startup call.
    """
    if _handler is not None:
        return
    try:
        size = int(config.get("LOG_BUFFER_SIZE", 0) or 0)
    except (TypeError, ValueError):
        return
    if size > 0:
        enable_log_capture(size=size, level=_resolve_level(config.get("LOG_BUFFER_LEVEL"), logging.INFO))
        if config.get("DEBUG"):
            emit(
                f"♣ Log capture armed late ({size} records); the narrative for "
                "this failure was not recorded. Call "
                "healing_agent.enable_log_capture() at startup to capture it."
            )
