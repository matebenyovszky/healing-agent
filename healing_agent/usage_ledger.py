"""What the model calls of one healing session cost.

A repair is rarely one model call: a hint, a fix, a retry after an invalid
candidate. The number worth knowing is their SUM for one session, which no
single call site can see — so the broker records each call here and the
artifact writers read the total.

Counts only: prompts and completions never enter the ledger, because it is
written to disk next to the repair and must stay as safe as the redacted
context beside it. Missing counts stay ``None`` rather than being estimated,
and no prices live here — they change faster than releases, so tokens are the
durable fact and the caller multiplies by a rate it controls.
"""

from contextvars import ContextVar
from typing import Any, Dict, List, Optional

#: A healing session makes a handful of calls; anything near this is a runaway
#: loop, and the ledger must not be what turns it into a memory problem.
MAX_RECORDS = 100

_calls: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar(
    "healing_agent_usage", default=None
)


def start() -> Any:
    """Open a fresh accounting scope. Returns a token for :func:`reset`."""
    return _calls.set([])


def reset(token: Any) -> None:
    """Close the scope opened by :func:`start`."""
    if token is not None:
        _calls.reset(token)


def record(
    provider: str,
    model: Optional[str],
    seconds: Optional[float] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
) -> None:
    """Add one model call. Silent no-op outside an accounting scope."""
    calls = _calls.get()
    if calls is None or len(calls) >= MAX_RECORDS:
        return
    calls.append({
        "provider": provider,
        "model": model,
        "seconds": seconds,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    })


def records() -> List[Dict[str, Any]]:
    """Every call recorded in the current scope, oldest first."""
    return list(_calls.get() or [])


def summary() -> Dict[str, Any]:
    """Totals for the current scope.

    A token total is ``None`` when no call reported that count, and otherwise
    sums the calls that did — with ``partial`` marking the difference, so a
    total is never silently read as complete.
    """
    calls = _calls.get() or []
    totals: Dict[str, Any] = {
        "calls": len(calls),
        "seconds": round(sum(c["seconds"] or 0 for c in calls), 3),
        "prompt_tokens": None,
        "completion_tokens": None,
        "partial": False,
    }
    for field in ("prompt_tokens", "completion_tokens"):
        reported = [c[field] for c in calls if c[field] is not None]
        if reported:
            totals[field] = sum(reported)
            totals["partial"] = totals["partial"] or len(reported) != len(calls)
    return totals


def describe() -> str:
    """One-line summary for artifact headers and debug output."""
    totals = summary()
    if not totals["calls"]:
        return "no model calls recorded"
    if totals["prompt_tokens"] is None and totals["completion_tokens"] is None:
        tokens = "tokens: not reported by this provider"
    else:
        prompt = totals["prompt_tokens"]
        completion = totals["completion_tokens"]
        tokens = (
            f"tokens in/out: {'?' if prompt is None else prompt}"
            f"/{'?' if completion is None else completion}"
            + (" (partial)" if totals["partial"] else "")
        )
    return f"{totals['calls']} model call(s), {totals['seconds']}s, {tokens}"
