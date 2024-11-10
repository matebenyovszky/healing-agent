import subprocess
import sys
import re
from typing import Optional, Tuple

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
        install_name = module_name
    elif match := re.search(optional_pattern, error_message):
        module_name = match.group(1)
        install_name = module_name
    
    if module_name:
        # Handle special cases where install name differs from import name
        special_cases = {
            "PIL": "pillow",
        }
        install_name = special_cases.get(module_name, install_name)
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
            print("♣ Could not extract module name from error message")
        return False
    
    module_name, install_name = module_info
    
    if debug:
        print(f"♣ Attempting to install missing module: {install_name}")
    
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", install_name],
            stdout=subprocess.PIPE if not debug else None,
            stderr=subprocess.PIPE if not debug else None
        )
        if debug:
            print(f"♣ Successfully installed {install_name}")
        return True
    except subprocess.CalledProcessError as e:
        if debug:
            print(f"♣ Failed to install {install_name}: {str(e)}")
        return False 