"""
Which evidence reaches which destination, and how much of it.

The same failure context travels to three places with very different economics:

    disk       an artifact meant to be searched later — space is nearly free
    provider   a prompt, paid for by the token, on every nested repair attempt
    issue      a GitHub body with a hard size limit, read by a human

A verification gate is a fourth reader, and it carries the `disk` selection: it
runs on the machine that already holds the artifacts, so it is the same trust
boundary rather than a separate one. It is named here because "governed by the
policy" has to be true of every destination — an exception is how evidence
leaks.

Redaction is NOT what varies here. One policy applies before anything leaves
the capture, so the evidence is equally safe in all three; a sink chooses how
much of it is worth carrying, not how safe it is.

    EVIDENCE = {
        "disk":     {"variables": 3000, "environment": 3000, "logs": 500},
        "provider": {"variables": 400,  "environment": 300,  "logs": 50},
        "issue":    {"variables": 300,  "environment": 300,  "logs": 50},
    }

A number means "include this section, with this limit"; `0` or a missing key
means the section is not carried to that sink. The unit differs by section
because the useful unit differs:

    variables, environment, arguments   characters per VALUE — every entry is
                                        kept and each is trimmed on its own, so
                                        one huge dataframe cannot push the rest
                                        of the state out of the report
    logs                                number of most recent LINES

The error, the traceback and the function's own source are never optional:
without them there is nothing to diagnose, and a repair prompt missing the
source cannot produce a repair. Only the sections above are negotiable.
"""

from typing import Any, Dict, Optional

#: Sections a sink may choose to carry, with the unit of their limit.
SECTIONS = ("arguments", "variables", "environment", "logs")

#: Where each section lives in a captured context.
_SECTION_KEYS = {
    "arguments": "function_arguments",
    "variables": "variables",
    "environment": "environment",
    "logs": "recent_logs",
}

DEFAULT_EVIDENCE: Dict[str, Dict[str, int]] = {
    "disk": {"arguments": 3000, "variables": 3000, "environment": 3000, "logs": 500},
    "provider": {"arguments": 1000, "variables": 400, "environment": 300, "logs": 50},
    "issue": {"arguments": 300, "variables": 300, "environment": 300, "logs": 50},
}


def policy(config: Optional[Dict[str, Any]], sink: str) -> Dict[str, int]:
    """Return the section limits for one sink, falling back to the defaults.

    A sink the configuration does not mention keeps its default rather than
    becoming empty: a typo in a sink name should cost a warning at most, never
    silently strip the evidence.
    """
    configured = (config or {}).get("EVIDENCE") or {}
    limits = dict(DEFAULT_EVIDENCE.get(sink, {}))
    for section, limit in (configured.get(sink) or {}).items():
        if section not in SECTIONS:
            continue
        try:
            limits[section] = max(0, int(limit))
        except (TypeError, ValueError):
            continue
    return limits


def wanted_anywhere(config: Optional[Dict[str, Any]], section: str) -> bool:
    """True when at least one sink carries this section.

    Capture is skipped entirely for a section nothing will use — the process
    environment is the expensive one, and reading it for nobody is waste.
    """
    return any(policy(config, sink).get(section, 0) > 0 for sink in DEFAULT_EVIDENCE)


def trim_value(value: Any, limit: int, depth: int = 0) -> Any:
    """Trim every string to ``limit``, entry by entry rather than in bulk.

    Public because the saved artifact needs it too: one implementation of
    "how evidence shrinks" rather than a copy per caller.
    """
    if depth > 25:
        return value
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + " …"
    if isinstance(value, dict):
        return {k: trim_value(v, limit, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [trim_value(v, limit, depth + 1) for v in value]
    if isinstance(value, tuple):
        return tuple(trim_value(v, limit, depth + 1) for v in value)
    return value


def select(
    context: Dict[str, Any], config: Optional[Dict[str, Any]], sink: str
) -> Dict[str, Any]:
    """Return the copy of ``context`` this sink should receive.

    Sections the sink does not carry are absent, not empty: a reader can tell
    "not collected" from "collected and empty".
    """
    limits = policy(config, sink)
    selected = {
        key: value
        for key, value in context.items()
        if key not in _SECTION_KEYS.values()
    }

    for section, key in _SECTION_KEYS.items():
        limit = limits.get(section, 0)
        if limit <= 0 or key not in context:
            continue
        value = context[key]
        if section == "logs":
            # A line count, not a character budget: what matters in a log is
            # how far back the narrative reaches.
            records = list(value or [])
            selected[key] = records[-limit:]
        else:
            selected[key] = trim_value(value, limit)

    return selected
