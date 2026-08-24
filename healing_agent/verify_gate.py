"""
Verification gates: judge a candidate before the live source file changes.

A gate is any command. Exit code 0 accepts the candidate, anything else
rejects it. Protocol-aware verifiers may read the redacted candidate context
from the ``HEALING_AGENT_CANDIDATE`` environment variable and print a JSON
object to stdout for detail, but the exit code alone decides.

    VERIFY_COMMAND = ["python", "checks/verify_loader.py"]   # one gate
    VERIFY_COMMAND = [["python", "checks/a.py"], ["ruff", "check"]]  # ordered gates

**Scope of the workspace.** The gate runs in a temporary directory that holds
the candidate file alone, with the repair already applied to it. That is
enough for a self-contained checker, and it is why a project-level test
command (``pytest tests/test_loader.py``) does NOT work here: the rest of the
project is not present. Full-project isolation — a filtered copy of the
working tree, so the tests run against exactly the code that is live plus the
candidate — is tracked separately in the roadmap.

A command that cannot start is a configuration error, not a verdict on the
candidate: it raises ``VerifyGateConfigurationError`` rather than quietly
rejecting every repair.
"""

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from . import workspace as workspace_module
from .code_replacer import function_replacer
from .console import emit


class VerifyGateConfigurationError(RuntimeError):
    """The gate itself is misconfigured, as opposed to the candidate failing.

    Kept distinct on purpose: a gate that cannot even start (a typo, a
    missing executable, several commands packed into one argument list)
    would otherwise look exactly like "the candidate is bad" and silently
    block every repair. Raising surfaces the operator error, while the
    decorator still re-raises the application's own exception.
    """


def verify_candidate(context: Dict[str, Any], fixed_code: str, config: Dict[str, Any]) -> bool:
    """Run configured verification gates before mutating the live file."""
    commands = _verify_commands(config.get("VERIFY_COMMAND"))
    if not commands:
        return True

    source = Path(context["error"]["file"])
    if not source.exists():
        emit(f"♣ Verify gate skipped missing source file: {source}")
        return False

    prepared = _prepare_workspace(source, config)
    if prepared is None:
        return False
    workspace, working_dir, candidate_path = prepared

    try:
        candidate_context = dict(context)
        candidate_context["error"] = dict(context.get("error", {}))
        candidate_context["error"]["file"] = str(candidate_path)
        candidate_context["fixed_code"] = fixed_code

        if not function_replacer(candidate_context, fixed_code):
            emit("♣ Verify gate could not apply candidate in isolated workspace.")
            return False

        env = os.environ.copy()
        env["HEALING_AGENT_CANDIDATE"] = json.dumps(
            {
                "protocol": "healing-agent-candidate-v1",
                "source_file": str(candidate_path),
                "original_file": str(source),
                "working_dir": str(working_dir),
                "context": candidate_context,
            },
            default=str,
        )

        for command in commands:
            if not _run_command_gate(command, working_dir, env, config):
                return False
        return True
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _prepare_workspace(source: Path, config: Dict[str, Any]):
    """Build the workspace the gates run in, honoring VERIFY_SCOPE.

    Returns ``(workspace_to_remove, working_dir, candidate_file)``. The project
    scope falls back to the file scope when the tree is too large to copy, so a
    misjudged scope degrades the gate's reach rather than failing the repair.
    """
    scope = str(config.get("VERIFY_SCOPE", "file")).lower()
    if scope not in {"file", "project"}:
        raise VerifyGateConfigurationError(
            f'VERIFY_SCOPE must be "file" or "project", got {scope!r}'
        )

    if scope == "project":
        prepared = workspace_module.copy_project(source)
        if prepared is not None:
            return prepared

    try:
        return workspace_module.copy_single_file(source)
    except OSError as copy_error:
        emit(f"♣ Verify gate could not prepare a workspace: {copy_error}")
        return None


def _verify_commands(value: Any) -> List[Any]:
    if value in (None, "", False):
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, Sequence):
        if all(isinstance(part, (str, os.PathLike)) for part in value):
            return [value]
        return list(value)
    return [value]


def _argv(command: Any) -> List[str]:
    if isinstance(command, (list, tuple)):
        return [str(part) for part in command]
    if isinstance(command, str):
        return [_strip_outer_quotes(part) for part in shlex.split(command, posix=(os.name != "nt"))]
    if isinstance(command, Iterable):
        return [str(part) for part in command]
    raise TypeError("VERIFY_COMMAND entries must be strings or argument lists")


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _run_command_gate(
    command: Any,
    workspace: Path,
    env: Dict[str, str],
    config: Dict[str, Any],
) -> bool:
    argv = _argv(command)
    if not argv:
        return True

    try:
        result = subprocess.run(
            argv,
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=float(config.get("VERIFY_TIMEOUT_SECONDS", 120)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        emit(f"♣ Verify gate timed out: {argv[0]}")
        return False
    except OSError as exc:
        raise VerifyGateConfigurationError(
            f"verify gate command could not start: {argv[0]!r} ({exc}). "
            "Check VERIFY_COMMAND - use an argument list, and a list of "
            "lists for several gates."
        ) from exc

    detail = _json_detail(result.stdout)
    if result.returncode == 0:
        if config.get("DEBUG") and detail:
            emit(f"♣ Verify gate detail: {detail}")
        return True

    message = detail.get("error") if detail else (result.stderr or result.stdout).strip()
    emit(f"♣ Verify gate rejected candidate: {message or 'command failed'}")
    return False


def _json_detail(stdout: str) -> Dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        detail = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return detail if isinstance(detail, dict) else {}
