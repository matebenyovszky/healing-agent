"""Project test runner.

This module delegates discovery and execution to pytest so only real tests are
counted and any failure produces a non-zero process exit code.
"""

import subprocess
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TESTS_DIR = PROJECT_ROOT / "tests"


def execute_tests(pytest_args: Sequence[str] = ()) -> int:
    """Run pytest and raise ``CalledProcessError`` when tests fail."""
    if not DEFAULT_TESTS_DIR.is_dir():
        raise FileNotFoundError(f"Tests directory not found: {DEFAULT_TESTS_DIR}")

    command = [
        sys.executable,
        "-m",
        "pytest",
        str(DEFAULT_TESTS_DIR),
        *pytest_args,
    ]
    print(f"Running tests with: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    return completed.returncode


if __name__ == "__main__":
    execute_tests(sys.argv[1:])
