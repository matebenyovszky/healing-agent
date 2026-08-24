"""
Secret redaction for captured context.

The healing agent captures a lot of runtime state (local/global variables,
function arguments, HTTP request/response headers, exception attributes) and
then (a) writes it to JSON files on disk and (b) sends it to an external LLM
provider. Any of those values could contain credentials.

This module performs *name-based* redaction: for every mapping we walk, if a
key / variable name / header name matches a sensitive pattern, its value is
replaced with a placeholder BEFORE the context is saved or sent anywhere.
Only values are redacted; keys and overall structure are preserved so the rest
of the pipeline keeps working.

Redaction is configurable via the config file:
    REDACT_SECRETS         : bool  -- master on/off switch (default: True)
    REDACT_EXTRA_PATTERNS  : list  -- extra regex/substring patterns to treat
                                      as sensitive (case-insensitive)
    REDACT_PLACEHOLDER     : str   -- replacement text (default: "<redacted>")
"""

import re
from collections.abc import Mapping
from typing import Any, Optional

DEFAULT_PLACEHOLDER = "<redacted>"

# Default sensitive field-name patterns (case-insensitive, matched as regex
# search against the key / variable / header name).
DEFAULT_SENSITIVE_PATTERNS = [
    r"pass(word|wd|phrase)?",
    r"secret",
    r"token",
    r"api[-_ ]?keys?",
    r"access[-_ ]?keys?",
    r"private[-_ ]?keys?",
    r"secret[-_ ]?keys?",
    r"client[-_ ]?secret",
    r"\bkeys?\b",
    r"auth(oriz|entic)?",       # authorization, authentication, auth
    r"bearer",
    r"credential",
    r"cookie",
    r"session[-_ ]?(id|key|token)",
    r"connection[-_ ]?string",
    r"conn[-_ ]?str",
    r"sas[-_ ]?token",
    r"passphrase",
]

# --- Value-level scrubbing --------------------------------------------------
# Name-based redaction is not enough for environment variables, the most
# secret-dense structure in a process: `DATABASE_URL` carries a password inside
# a URL, `SENTRY_DSN` embeds a key, and a licence variable may hold a JWT. None
# of those names look sensitive. These patterns catch the value instead.

_URL_CREDENTIALS = re.compile(
    r"(?P<scheme>[a-zA-Z][\w+.-]*://)(?P<user>[^:/@\s]+)(?::(?P<password>[^@/\s]+))?@"
)

_SECRET_SHAPES = re.compile(
    r"("
    r"gh[pousr]_[A-Za-z0-9]{16,}"                                        # GitHub
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|sk-[A-Za-z0-9_-]{16,}"                                            # OpenAI style
    r"|(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}"                      # Stripe style
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"                                     # Slack
    r"|AKIA[0-9A-Z]{16}"                                                 # AWS key id
    r"|ya29\.[A-Za-z0-9_-]{20,}"                                         # Google OAuth
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{5,}"       # JWT
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"                               # PEM
    r")"
)


def scrub_value(text: Any, placeholder: str = DEFAULT_PLACEHOLDER) -> Any:
    """Mask secrets that hide in a VALUE rather than in its name.

    Returns the text with URL credentials and recognisable token shapes
    replaced. Anything unrecognised is returned untouched: this is a denylist,
    and the honest limit is that a bespoke secret format under a harmless name
    will pass. Add its name to ``REDACT_EXTRA_PATTERNS`` when you have one.
    """
    if not isinstance(text, str) or not text:
        return text

    def _mask_credentials(match):
        # A lone userinfo is masked too: in a configuration value it is far
        # more often a key (a Sentry DSN, a tokenised git remote) than a
        # username. Scheme, host and path survive, which is the diagnostic part.
        if match.group("password"):
            return f"{match.group('scheme')}{match.group('user')}:{placeholder}@"
        return f"{match.group('scheme')}{placeholder}@"

    scrubbed = _URL_CREDENTIALS.sub(_mask_credentials, text)
    return _SECRET_SHAPES.sub(placeholder, scrubbed)


# Guard against pathological / self-referential structures.
_MAX_DEPTH = 25


def _build_matcher(patterns) -> "re.Pattern":
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def get_sensitive_matcher(config: Optional[dict] = None) -> "re.Pattern":
    """Build the compiled matcher, merging any user-supplied extra patterns."""
    patterns = list(DEFAULT_SENSITIVE_PATTERNS)
    if config:
        extra = config.get("REDACT_EXTRA_PATTERNS") or []
        if isinstance(extra, (list, tuple)):
            patterns.extend(str(p) for p in extra)
    return _build_matcher(patterns)


def is_sensitive_name(name: Any, matcher: "re.Pattern") -> bool:
    """True if the given key/name looks sensitive."""
    return bool(name is not None and matcher.search(str(name)))


def _redact(obj: Any, matcher: "re.Pattern", placeholder: str, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return obj

    if isinstance(obj, Mapping):
        result = {}
        for key, value in obj.items():
            if is_sensitive_name(key, matcher):
                result[key] = placeholder
            else:
                result[key] = _redact(value, matcher, placeholder, depth + 1)
        return result

    if isinstance(obj, list):
        return [_redact(v, matcher, placeholder, depth + 1) for v in obj]

    if isinstance(obj, tuple):
        return tuple(_redact(v, matcher, placeholder, depth + 1) for v in obj)

    return obj


def redact(context: Any, config: Optional[dict] = None) -> Any:
    """
    Return a redacted copy of ``context``.

    Any value stored under a sensitive-looking key/name is replaced with the
    configured placeholder. Non-mapping/list/tuple values are returned as-is.
    If redaction is disabled via config (``REDACT_SECRETS = False``) the input
    is returned unchanged.
    """
    if config is not None and config.get("REDACT_SECRETS", True) is False:
        return context

    placeholder = DEFAULT_PLACEHOLDER
    if config:
        placeholder = config.get("REDACT_PLACEHOLDER") or DEFAULT_PLACEHOLDER

    matcher = get_sensitive_matcher(config)
    return _redact(context, matcher, placeholder, 0)
