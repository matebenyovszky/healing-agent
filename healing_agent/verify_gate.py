import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .code_replacer import function_replacer
from .console import emit


def verify_candidate(context: Dict[str, Any], fixed_code: str, config: Dict[str, Any]) -> bool:
    """Run configured verification gates before mutating the live file."""
    commands = _verify_commands(config.get("VERIFY_COMMAND"))
    if not commands:
        return True

    source = Path(context["error"]["file"])
    if not source.exists():
        emit(f"♣ Verify gate skipped missing source file: {source}")
        return False

    with tempfile.TemporaryDirectory(prefix="healing-agent-verify-") as workspace:
        workspace_path = Path(workspace)
        candidate_path = workspace_path / source.name
        shutil.copy2(source, candidate_path)

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
                "context": candidate_context,
            },
            default=str,
        )

        for command in commands:
            if not _run_command_gate(command, workspace_path, env, config):
                return False

    return True


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
        emit(f"♣ Verify gate could not start {argv[0]!r}: {exc}")
        return False

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
