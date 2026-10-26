import logging
import subprocess
import sys
import re
from typing import Optional, Tuple
from ..console import emit

# A bare distribution name. Anything else that can follow `pip install` - an
# option (`--index-url=...`), a direct URL (`x @ https://...`), a path, a
# version specifier - is refused: the name comes from an exception MESSAGE,
# and a message can quote data the program received.
_INSTALLABLE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")

#: pip resolving against a slow index must not hang the failing application.
PIP_TIMEOUT_SECONDS = 300


def extract_module_info(error_message: str) -> Optional[Tuple[str, str]]:
    """
    Extract module name and suggested install command from error message.
    Returns tuple of (module_name, install_name) or None if not found.
    """
    # Pattern for "No module named 'x'"
    module_pattern = r"No module named '(.+?)'"
    # Pattern for "Missing optional dependency 'x'. Use pip or conda to install x"
    optional_pattern = r"Missing optional dependency '(.+?)'\."

    module_name = None
    install_name = None

    if match := re.search(module_pattern, error_message):
        module_name = match.group(1)
    elif match := re.search(optional_pattern, error_message):
        module_name = match.group(1)

    if module_name:
        # `No module named 'a.b'` is missing the distribution that provides
        # the top-level package `a`; `pip install a.b` names nothing real.
        install_name = module_name.split('.')[0]
        # Handle special cases where install name differs from import name
        special_cases = {
            "PIL": "pillow",
        }
        install_name = special_cases.get(install_name, install_name)
        if not _INSTALLABLE_NAME.fullmatch(install_name):
            return None
        return (module_name, install_name)

    return None

def install_missing_module(error_message: str, debug: bool = False) -> bool:
    """
    Attempts to install a missing module using pip.
    Returns True if installation was successful.
    """
    module_info = extract_module_info(error_message)
    if not module_info:
        if debug:
            emit("♣ Could not extract module name from error message", level=logging.ERROR)
        return False

    module_name, install_name = module_info

    if debug:
        emit(f"♣ Attempting to install missing module: {install_name}")

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", install_name],
            # DEVNULL, not PIPE: check_call never reads a pipe, so pip's
            # output filling it would block the install forever.
            stdout=subprocess.DEVNULL if not debug else None,
            stderr=subprocess.DEVNULL if not debug else None,
            timeout=PIP_TIMEOUT_SECONDS,
        )
        if debug:
            emit(f"♣ Successfully installed {install_name}")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        if debug:
            emit(f"♣ Failed to install {install_name}: {str(e)}", level=logging.ERROR)
        return False
