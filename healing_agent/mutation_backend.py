import json
import shlex
import subprocess
from typing import Dict, Optional

from .code_replacer import function_replacer


def apply_mutation(context: Dict, fixed_code: str, config: Dict) -> bool:
    """Apply a generated repair through the configured mutation backend.

    The default backend preserves Healing Agent's existing behavior. The
    command backend is intentionally generic so external safe-mutation systems
    can validate, sandbox, apply, and roll back without becoming a package
    dependency.
    """
    backend = str(config.get("MUTATION_BACKEND", "direct")).lower()
    if backend == "direct":
        return function_replacer(context, fixed_code)
    if backend == "command":
        return apply_command_backend(context, fixed_code, config)
    print(f"♣ Unknown mutation backend: {backend}")
    return False


def apply_command_backend(context: Dict, fixed_code: str, config: Dict) -> bool:
    command = config.get("MUTATION_COMMAND")
    if not command:
        print("♣ MUTATION_BACKEND='command' requires MUTATION_COMMAND")
        return False

    argv = shlex.split(command) if isinstance(command, str) else list(command)
    payload = {
        "protocol_version": "healing-agent-mutation-v1",
        "backend": "command",
        "source_file": context["error"]["file"],
        "function_name": context["function_info"]["name"],
        "fixed_code": fixed_code,
        "error": context.get("error", {}),
        "function_info": context.get("function_info", {}),
    }
    try:
        result = subprocess.run(
            argv,
            input=json.dumps(payload, sort_keys=True),
            text=True,
            capture_output=True,
            timeout=float(config.get("MUTATION_TIMEOUT_SECONDS", 120)),
            check=False,
        )
    except Exception as exc:
        print(f"♣ Mutation command failed to start: {exc}")
        return False

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        print(f"♣ Mutation command rejected repair: {detail}")
        return False

    response = _parse_response(result.stdout)
    if response is None:
        return False
    if response.get("ok") is True:
        return True

    detail = response.get("error") or response.get("detail") or "repair rejected"
    rolled_back = response.get("rolled_back")
    print(f"♣ Mutation command rejected repair: {detail}; rolled_back={rolled_back}")
    return False


def _parse_response(stdout: str) -> Optional[Dict]:
    try:
        response = json.loads(stdout or "{}")
    except json.JSONDecodeError as exc:
        print(f"♣ Mutation command returned invalid JSON: {exc}")
        return None
    if not isinstance(response, dict):
        print("♣ Mutation command must return a JSON object")
        return None
    return response
