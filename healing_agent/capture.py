"""
Explicit context capture — evidence without a failure.

The machinery that records what a program was doing already exists and is
already exception-free: `capture_context(error=None)` tags its result
`capture_type: "debug"`. Until now only the decorator could reach it, and only
when something raised. `capture()` exposes the same evidence at any point in
the code:

    import healing_agent

    response = requests.get(url)
    healing_agent.capture("supplier response")   # snapshot, no AI, no mutation

The snapshot is redacted through the same chokepoint as a failure context and
written next to the calling module in `_healing_agent_captures/`. Nothing is
sent to a provider and no code is modified: this is observation, not healing.
"""

import logging
import datetime
import inspect
import json
import os
import re
from typing import Any, Dict, Optional

from .console import emit
from .exception_handler import capture_context
from .redactor import redact

CAPTURE_DIR_NAME = "_healing_agent_captures"


def _slug(label: Optional[str]) -> str:
    """Make a label safe for a filename."""
    if not label:
        return "capture"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(label)).strip("_")
    return cleaned[:60] or "capture"


def save_capture(context: Dict[str, Any], directory: str, label: Optional[str]) -> Optional[str]:
    """Write a capture snapshot as JSON. Returns the path, or None on failure."""
    file_path = None
    try:
        capture_dir = os.path.join(directory, CAPTURE_DIR_NAME)
        os.makedirs(capture_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_path = os.path.join(capture_dir, f"{timestamp}_{_slug(label)}.json")
        try:
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(context, handle, indent=2, ensure_ascii=False, default=str)
        except Exception as write_error:
            emit(f"♣ Failed to write capture to {file_path}: {write_error}", level=logging.ERROR)
            file_path = None
    except Exception as save_error:
        emit(f"♣ Failed to save capture: {save_error}", level=logging.ERROR)
        file_path = None
    return file_path


def capture(label: Optional[str] = None, **local_config) -> Optional[str]:
    """Save a redacted snapshot of the calling frame's context.

    Args:
        label: Short name for the snapshot; becomes part of the filename.
        **local_config: Overrides merged over the loaded configuration, e.g.
            `REDACT_SECRETS=False` or `CAPTURE_DIR="/tmp"`.

    Returns:
        The path of the written snapshot, or None if capturing failed.
        Capturing never raises: observation must not break the program it
        observes.
    """
    try:
        caller = inspect.currentframe().f_back
        if caller is None:
            emit("♣ Capture skipped: no caller frame available")
            return None

        try:
            from .config_loader import load_config

            config, _ = load_config()
        except Exception:
            # Observation should work even without a usable provider config.
            config = {}
        config.update(local_config)

        context = capture_context(config=config, error=None, frame=caller)
        context["capture_label"] = label
        context["source"] = {
            "file": caller.f_code.co_filename,
            "line": caller.f_lineno,
            "function": caller.f_code.co_name,
        }

        recent_logs = _recent_logs(config)
        if recent_logs:
            context["recent_logs"] = recent_logs

        context = redact(context, config)

        directory = config.get("CAPTURE_DIR") or os.path.dirname(
            os.path.abspath(caller.f_code.co_filename)
        )
        from .evidence import select

        path = save_capture(select(context, config, 'disk'), str(directory), label)
        if path and config.get("DEBUG"):
            emit(f"♣ Capture saved to: {path}")
        return path

    except Exception as capture_error:
        emit(f"♣ Capture failed: {capture_error}")
        return None


def _recent_logs(config: Dict[str, Any]):
    """Attach buffered application log lines when log capture is armed."""
    try:
        from .log_buffer import recent_records

        return recent_records(config)
    except Exception:
        return None
