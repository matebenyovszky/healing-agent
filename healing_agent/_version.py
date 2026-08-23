"""Version information for Healing Agent — the single source of truth.

Two versions live here, and they are deliberately INDEPENDENT:

``__version__``
    The distribution version. It is never written down in Python source:
    it is read from the installed package metadata, so ``pyproject.toml``
    stays the only place the number is maintained.

``CONFIG_SCHEMA_VERSION``
    Describes the shape of :mod:`healing_agent.config_template` — which
    configuration keys exist. It is bumped ONLY when a key is added, renamed
    or removed, never on a release that leaves the configuration untouched.

Why not one number for both? Because the question a user's config file has to
answer is not "which release am I from?" but "does this code need keys I do not
have?". Mirroring the distribution version made every patch release declare
every existing config file outdated, which trains people to ignore the warning.

The value of ``CONFIG_SCHEMA_VERSION`` is nevertheless expressed as the release
in which the schema LAST CHANGED. That keeps it self-documenting ("the config
layout introduced in 0.4.0"), keeps it directly comparable with the marker
already written into every config file in the wild, and still leaves it
unchanged across releases that add no keys.
"""

from importlib.metadata import PackageNotFoundError, version as _distribution_version
from typing import Tuple

#: Configuration schema version. Bump ONLY when config_template.py gains,
#: renames or removes a key, and set it to the release that ships that change.
#: ``tests/test_version.py`` enforces that config_template.py agrees with this.
CONFIG_SCHEMA_VERSION = "0.4.0"

try:
    __version__ = _distribution_version("healing_agent")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0.dev0"


def parse_version(value: object) -> Tuple[int, ...]:
    """Return a comparable tuple for a dotted version string.

    Unparseable input yields ``()``, which compares as older than every real
    version. That is the intended reading: a config whose marker is missing or
    malformed is treated as predating the schema, not as up to date.
    """
    if not isinstance(value, str):
        return ()
    parts = []
    for chunk in value.strip().split("."):
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


__all__ = ["__version__", "CONFIG_SCHEMA_VERSION", "parse_version"]
