"""
What was tried, and why each attempt failed.

An escalated issue used to show a candidate with no indication that it had been
REJECTED, no reason, and no trace of the attempts after the first. That is
worse than showing nothing: a reader — human or an issue→PR agent — would take
the candidate for the repair rather than for a direction already known to fail.

The ledger records one entry per attempt: what was generated, what happened to
it, and the detail that explains the verdict. It exists because three separate
consumers need exactly this record:

    the escalated issue   so a rejected candidate is signal, not noise
    a pull request body   so a reviewer sees what verified the change
    incident memory       so "this class was healed by X, and X no longer
                          works" is expressible

Entries are redacted as they are recorded. A gate's detail comes from a
subprocess the operator configured, and its output can quote data from the
candidate workspace, so it is not trusted to be clean merely because
Healing Agent produced the surrounding entry.
"""

from typing import Any, Dict, List, Optional

#: Why an attempt ended. The wording is what a reader sees, so it states the
#: verdict rather than the internal branch that produced it.
OUTCOMES = {
    "no_candidate": "no candidate was generated",
    "gate_rejected": "rejected by a verify gate",
    "apply_failed": "candidate could not be applied",
    "still_failed": "applied, but the function still failed",
    "not_applied": "not applied (AUTO_FIX is off)",
    "healed": "accepted",
}

#: A candidate is shown in full up to this length; beyond it the reader is
#: better served by the artifact on disk than by a wall of code in an issue.
CANDIDATE_CHARS = 1200


def entry(
    attempt: int,
    outcome: str,
    candidate: Optional[str] = None,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    """Build one ledger entry."""
    return {
        "attempt": attempt,
        "outcome": outcome,
        "summary": OUTCOMES.get(outcome, outcome),
        "candidate": candidate,
        "detail": detail,
    }


def ordered(attempts: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Return the entries in ATTEMPT order, which is not the order they arrive.

    Repair attempts nest: a repaired function that fails again re-enters the
    decorator, so attempt 2 completes — and therefore records — inside attempt
    1. Left alone the ledger reads backwards, which inverts the one thing it
    exists to convey: what was tried, and what was tried instead.
    """
    if not attempts:
        return []
    return sorted(attempts, key=lambda record: record.get("attempt") or 0)


def render(attempts: Optional[List[Dict[str, Any]]], candidate_chars: int = CANDIDATE_CHARS) -> List[str]:
    """Render the ledger as Markdown lines, or an empty list when there is none.

    Ordered oldest first, because the value is the sequence: what was tried,
    what that produced, and what was tried instead.
    """
    if not attempts:
        return []

    lines = ["", "### Repair attempts", ""]
    for record in ordered(attempts):
        number = record.get("attempt", "?")
        lines.append(f"**Attempt {number}** — {record.get('summary', record.get('outcome'))}")
        detail = record.get("detail")
        if detail:
            lines += ["", f"> {str(detail).strip()}"]
        candidate = record.get("candidate")
        if candidate:
            shown = str(candidate).rstrip()
            if len(shown) > candidate_chars:
                shown = shown[:candidate_chars] + "\n… truncated; full candidate in _healing_agent_fixes/"
            lines += ["", "<details><summary>Candidate</summary>", "", "```python", shown, "```", "", "</details>"]
        lines.append("")

    accepted = any(record.get("outcome") == "healed" for record in attempts)
    if not accepted:
        lines += [
            "Every candidate above was rejected, so none of these directions "
            "is the repair — they are the directions already known to fail.",
            "",
        ]
    return lines
