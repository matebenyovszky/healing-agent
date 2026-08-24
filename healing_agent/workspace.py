"""
Isolated workspaces: a place to judge a candidate before the live tree changes.

Two scopes exist, and the difference decides what a gate can actually check:

``file``
    A temporary directory holding the candidate file alone. Cheap, always
    available, enough for a self-contained checker.

``project``
    A filtered copy of the project as it exists RIGHT NOW, with the candidate
    applied to its copy of the source file. This is what an application's own
    test suite needs, because a test imports siblings, reads fixtures and
    expects its package layout to be present.

The project scope copies the WORKING TREE rather than using ``git worktree``
on purpose. A worktree checks out ``HEAD``, so with uncommitted changes — the
normal state of a machine someone is working on — the gate would pass judgment
on code other than the code that is actually running. A filtered copy is
slower and less clever, and it is the only variant whose verdict is about the
program in front of us.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Optional, Tuple

from .console import emit

#: Directories never worth copying: recreatable, huge, or artifacts of ours.
DEFAULT_EXCLUDES = (
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "_healing_agent_backups",
    "_healing_agent_exceptions",
    "_healing_agent_fixes",
    "_healing_agent_captures",
)

#: Refuse rather than copy a data lake by accident. A project that legitimately
#: exceeds this should exclude its data directory or use the file scope.
DEFAULT_MAX_FILES = 20000
DEFAULT_MAX_BYTES = 500 * 1024 * 1024


def find_project_root(source: Path) -> Path:
    """Return the directory that should be treated as the project root.

    The git root when there is one, because that is the boundary a test suite
    is usually written against; otherwise the file's own directory, which keeps
    the copy small instead of guessing upwards.
    """
    directory = source.parent.resolve()
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            return candidate
    return directory


def _excluded(name: str, excludes: Iterable[str]) -> bool:
    return name in set(excludes)


def measure_tree(root: Path, excludes: Iterable[str]) -> Tuple[int, int]:
    """Return (file count, total bytes) of what a copy would include."""
    files = 0
    total = 0
    excluded = set(excludes)
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in excluded]
        for name in filenames:
            if name.endswith((".pyc", ".pyo")):
                continue
            files += 1
            try:
                total += (Path(current) / name).stat().st_size
            except OSError:
                pass
    return files, total


def copy_project(
    source: Path,
    excludes: Iterable[str] = DEFAULT_EXCLUDES,
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Optional[Tuple[Path, Path, Path]]:
    """Copy the project containing ``source`` into a temporary directory.

    Returns ``(workspace, project_copy, candidate_file)``, or None when the
    tree is too large to copy — refusing is better than stalling a repair for
    minutes, and the caller can fall back to the file scope.

    The caller owns ``workspace`` and must remove it.
    """
    source = Path(source).resolve()
    root = find_project_root(source)

    files, total = measure_tree(root, excludes)
    if files > max_files or total > max_bytes:
        emit(
            f"♣ Project too large for an isolated copy "
            f"({files} files, {total // (1024 * 1024)} MB at {root}); "
            "using the single-file scope instead. Exclude data directories or "
            "set VERIFY_SCOPE=\"file\" to silence this."
        )
        return None

    workspace = Path(tempfile.mkdtemp(prefix="healing-agent-project-"))
    try:
        project_copy = workspace / root.name
        shutil.copytree(
            root,
            project_copy,
            symlinks=True,
            ignore=shutil.ignore_patterns(*excludes, "*.pyc", "*.pyo"),
        )
        candidate_file = project_copy / source.relative_to(root)
        if not candidate_file.exists():
            raise FileNotFoundError(f"source not found in the copy: {candidate_file}")
        return workspace, project_copy, candidate_file
    except Exception as copy_error:
        shutil.rmtree(workspace, ignore_errors=True)
        emit(f"♣ Could not create an isolated project copy: {copy_error}")
        return None


def copy_single_file(source: Path) -> Tuple[Path, Path, Path]:
    """Copy just ``source`` into a temporary directory.

    Returns ``(workspace, working_dir, candidate_file)`` so callers can treat
    both scopes identically. The caller owns ``workspace``.
    """
    source = Path(source).resolve()
    workspace = Path(tempfile.mkdtemp(prefix="healing-agent-verify-"))
    candidate_file = workspace / source.name
    shutil.copy2(source, candidate_file)
    return workspace, workspace, candidate_file
