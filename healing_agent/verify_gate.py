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
from typing import Any, Dict, Iterable, List, Sequence, Optional

from .code_replacer import function_replacer
from .evidence import select
from .console import emit


class VerifyGateConfigurationError(RuntimeError):
    """The gate itself is misconfigured, as opposed to the candidate failing.

    Kept distinct on purpose: a gate that cannot even start (a typo, a
    missing executable, several commands packed into one argument list)
    would otherwise look exactly like "the candidate is bad" and silently
    block every repair. Raising surfaces the operator error, while the
    decorator still re-raises the application's own exception.
    """


def verify_candidate(
    context: Dict[str, Any],
    fixed_code: str,
    config: Dict[str, Any],
    report: Optional[Dict[str, Any]] = None,
) -> bool:
    """Run configured verification gates before mutating the live file.

    Args:
        report: Optional dict the gate fills with ``reason`` when it
            rejects. The verdict itself is the useful half of a rejection -
            "a gate said no" tells a reader nothing, "expected 2000, got 0"
            tells them where to look - so it is reported rather than
            discarded.
    """
    commands = _verify_commands(config.get("VERIFY_COMMAND"))
    if not commands:
        return True

    source = Path(context["error"]["file"])
    if not source.exists():
        emit(f"♣ Verify gate skipped missing source file: {source}")
        return False

    with tempfile.TemporaryDirectory(prefix="healing-agent-verify-") as workspace:
        working_dir = Path(workspace)
        candidate_path = working_dir / source.name
        shutil.copy2(source, candidate_path)

        candidate_context = dict(context)
        candidate_context["error"] = dict(context.get("error", {}))
        candidate_context["error"]["file"] = str(candidate_path)
        candidate_context["fixed_code"] = fixed_code

        if not function_replacer(candidate_context, fixed_code):
            emit("♣ Verify gate could not apply candidate in isolated workspace.")
            return False

        # A gate command is a fourth destination for the evidence, not an
        # exception to the policy that governs the other three. It runs on the
        # machine that already holds the artifacts, so it carries the `disk`
        # selection — and an operator who trims `disk` now trims this too,
        # instead of having the full context handed to a subprocess and to
        # everything that subprocess starts.
        env = os.environ.copy()
        env["HEALING_AGENT_CANDIDATE"] = json.dumps(
            {
                "protocol": "healing-agent-candidate-v1",
                "source_file": str(candidate_path),
                "original_file": str(source),
                "context": select(candidate_context, config, "disk"),
            },
            default=str,
        )

        for command in commands:
            if not _run_command_gate(command, working_dir, env, config, report):
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
    report: Optional[Dict[str, Any]] = None,
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
        if report is not None:
            report["reason"] = f"{argv[0]} timed out"
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
    message = message or "command failed"
    emit(f"♣ Verify gate rejected candidate: {message}")
    if report is not None:
        report["reason"] = f"{argv[0]} exited {result.returncode}: {message}"
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
