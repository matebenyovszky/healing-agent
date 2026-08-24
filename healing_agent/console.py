"""Healing Agent's output: the application's logging when it has any, print otherwise.

Two problems are solved in one place, because there is exactly one place all
library output passes through.

**Never break the supervised application.** Healing Agent's messages use
decorative characters (♣, ⚕️, ✧). On a console whose encoding cannot represent
them — cp1252 on Windows is the common case, and any redirected stdout inherits
the locale encoding — a plain `print()` raises `UnicodeEncodeError`. Inside the
healing path that exception would replace the application's own error, which
breaks this project's central promise. `emit()` therefore degrades instead of
raising, and the logging path has the same property for free: the `logging`
module swallows handler errors by design.

**Inherit the host application's logging.** Records go to
`logging.getLogger("healing_agent")`, which is never configured here. Level,
handlers, formatters and filters all come from whatever the application set up,
through the standard logger hierarchy — that IS the inheritance mechanism, and
it is why no third-party logger becomes a dependency: loguru users install their
documented `InterceptHandler`, structlog wraps stdlib, and plain
`logging.basicConfig()` just works.

An application that configured nothing would be left silent by that rule, which
would be a regression from the rich console narration this project is used for.
So the choice is made per call, from observable facts:

    auto (default)  route to the logger when the application has configured
                    logging for our records, print when it has not
    logging         always route to the logger
    print           always print, whatever the application configured

`LOG_MODE` in the config file selects the mode; `set_output_mode()` is the
programmatic equivalent and is what the test suite pins.
"""

import logging
import sys

LOGGER_NAME = "healing_agent"
MODES = ("auto", "logging", "print")

_logger = logging.getLogger(LOGGER_NAME)
_mode = "auto"

# Decoration belongs to the console. A log record already carries its level and
# timestamp from the application's formatter, so these prefixes are stripped
# rather than duplicated.
_PREFIXES = ("♣ ", "⚠ ", "♣", "⚠")


def set_output_mode(mode: str) -> None:
    """Select where output goes. Unknown values fall back to ``auto``."""
    global _mode
    _mode = mode if mode in MODES else "auto"


def get_output_mode() -> str:
    """Return the active output mode."""
    return _mode


def _application_configured_logging() -> bool:
    """True when a record sent to our logger would reach the APPLICATION.

    Walks the hierarchy exactly as propagation does, so this answers the real
    question — will the application see this message? — rather than guessing
    from which logger happens to be configured.

    Handlers Healing Agent installed on the application's behalf do not count.
    The log ring buffer (see log_buffer.py) attaches to the root logger, and
    treating it as "the application configured logging" would silence the
    console the moment log capture is armed.
    """
    try:
        logger = _logger
        while logger:
            if any(
                not getattr(handler, "_healing_agent_internal", False)
                for handler in logger.handlers
            ):
                return True
            if not logger.propagate:
                return False
            logger = logger.parent
    except Exception:
        pass
    return False


def _use_logging() -> bool:
    if _mode == "logging":
        return True
    if _mode == "print":
        return False
    return _application_configured_logging()


def _strip_decoration(message: str) -> str:
    for prefix in _PREFIXES:
        if message.startswith(prefix):
            return message[len(prefix):].lstrip()
    return message


def _safe_print(message: str, end: str) -> None:
    """Print, degrading to a lossy transliteration rather than raising."""
    try:
        print(message, end=end)
        return
    except UnicodeEncodeError:
        pass
    except Exception:
        return

    try:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        safe = message.encode(encoding, errors="replace").decode(
            encoding, errors="replace"
        )
        print(safe, end=end)
    except Exception:
        # Output is best-effort: a reporting problem must never surface as the
        # application's failure.
        pass


def emit(*args, sep: str = " ", end: str = "\n", level: int = logging.INFO) -> None:
    """Report a Healing Agent message without ever raising.

    Args:
        level: Only consulted on the logging path, where the application's
            configuration decides what survives. The print path is unfiltered,
            exactly as it was before logging existed, so console behavior does
            not change for an application that configured nothing.
    """
    try:
        message = sep.join(str(part) for part in args)
    except Exception:
        return

    if _use_logging():
        try:
            _logger.log(level, _strip_decoration(message))
            return
        except Exception:
            # Fall through to printing rather than losing the message.
            pass

    _safe_print(message, end)
