"""
Console output that can never break the supervised application.

Healing Agent's messages use decorative characters (♣, ⚕️, ✧). On a console
whose encoding cannot represent them — cp1252 on Windows is the common case,
and any redirected stdout inherits the locale encoding — a plain `print()`
raises `UnicodeEncodeError`. Inside the healing path that exception would
replace the application's own error, which breaks this project's central
promise that the original exception is always what propagates.

`emit()` is a drop-in replacement for `print()` that degrades instead of
raising: it prints normally when the encoding allows, falls back to a lossy
transliteration when it does not, and swallows anything else. Reporting is
never worth a crash.
"""

import sys


def emit(*args, sep: str = " ", end: str = "\n") -> None:
    """Print a Healing Agent message, degrading rather than raising."""
    try:
        print(*args, sep=sep, end=end)
        return
    except UnicodeEncodeError:
        pass
    except Exception:
        return

    try:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        message = sep.join(str(part) for part in args)
        safe = message.encode(encoding, errors="replace").decode(
            encoding, errors="replace"
        )
        print(safe, end=end)
    except Exception:
        # Output is best-effort: a reporting problem must never surface as the
        # application's failure.
        pass
