"""
Ask for healing from a handled error branch.

Not every failure worth repairing arrives as an exception. A loader often
*detects* the problem itself — a column is missing, a payload has the wrong
shape, a date will not parse — and handles it in an ``if``. Until now that code
had no way to reach the healing loop: only an escaping exception triggered it.

``request_healing`` closes that gap without adding a second pipeline. It raises
``HealingRequested``, which the decorator catches like any other exception, so
observation, redaction, hint generation, the fix prompt, the verify gates,
apply, restore-on-failure and escalation all behave exactly as they already do.
The only difference is what the model is told: that the program asked for a
repair deliberately, and why.

    @healing_agent
    def load_sales(rows):
        if "amount" not in rows[0]:
            healing_agent.request_healing(
                "input has no 'amount' column; headers: " + ", ".join(rows[0])
            )
        ...

If healing succeeds the repaired function's result is returned to the caller.
If it does not, ``HealingRequested`` propagates — the program asked a question
and deserves to hear that it went unanswered, rather than receiving a silent
``None``.
"""

from typing import Any, Optional


class HealingRequested(Exception):
    """Raised by application code to ask for a repair of the current function.

    Carries the reason the program gives for wanting one, which is what makes
    this more useful to the model than an ordinary exception: the failing line
    describes a symptom, while the reason describes the intent.
    """

    def __init__(self, reason: str, details: Optional[Any] = None):
        self.reason = reason
        self.details = details
        message = f"healing requested: {reason}"
        if details is not None:
            message = f"{message} (details: {details})"
        super().__init__(message)


def request_healing(reason: str, details: Optional[Any] = None) -> None:
    """Ask Healing Agent to repair the function this is called from.

    Args:
        reason: Why a repair is wanted, in the program's own words. This is
            passed to the model, so state what was expected and what arrived.
        details: Optional structured extra evidence (a header list, a schema,
            a sample record). Redacted like any other captured value.

    Raises:
        HealingRequested: always. Control leaves the function at this point,
            exactly as an exception would, which is deliberate: healing works
            by replacing the function and calling it again.
    """
    raise HealingRequested(reason, details)
