import inspect
import logging
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Dict, Optional

from .agent_tools.tool_install_missing_module import install_missing_module
from .ai_code_fixer import fix
from .ai_fix_saver import save_ai_fix
from .ai_hint_generator import generate_hint
from .code_backup import create_backup, restore_backup
from .code_replacer import function_replacer
from .config_loader import load_config
from .exception_handler import capture_context
from .exception_saver import save_context
from .git_patch_saver import apply_git_patch, save_git_patch
from .github_issue import open_issue_for_failure
from .log_buffer import arm_from_config_if_requested, recent_records
from .redactor import redact
from .request import HealingRequested
from .console import emit
from .verify_gate import verify_candidate
from . import usage_ledger


# The default must NOT be a mutable dict: a ContextVar default is a single
# object shared by every context that never set the variable, so an in-place
# mutation anywhere would leak attempt counts across unrelated healing runs.
# None means "no attempts recorded yet" and is read through _current_attempts().
_repair_attempts: ContextVar[Optional[Dict[str, int]]] = ContextVar(
    "healing_agent_repair_attempts", default=None
)

# Tracks the outermost healing session so a definitive failure can restore the
# pre-healing sources. Repair attempts nest (a repaired function that fails
# again re-enters the decorator), so only the outermost invocation owns the
# session and performs the restore.
_healing_session: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "healing_agent_session", default=None
)


def _repair_key(func: Callable[..., Any]) -> str:
    """Return a stable key across reloads of the decorated function."""
    return f"{func.__module__}:{func.__qualname__}"


def _current_attempts() -> Dict[str, int]:
    """Return the attempt counters for this context, never the shared default."""
    return _repair_attempts.get() or {}


def _register_backup(file_path: str, backup_path: Optional[str]) -> None:
    """Remember the FIRST backup taken per file in this healing session."""
    session = _healing_session.get()
    if session is None or not backup_path or not file_path:
        return
    session["backups"].setdefault(file_path, backup_path)


def _register_failure_context(context: Dict[str, Any]) -> None:
    """Keep the FIRST captured context of the session for escalation.

    Later attempts describe failures of the agent's own candidates; the first
    one is the original application error that will be re-raised.
    """
    session = _healing_session.get()
    if session is None:
        return
    session.setdefault("context", context)


def _restore_session_sources(session: Dict[str, Any]) -> None:
    """Undo every file mutation performed during a failed healing session."""
    for file_path, backup_path in session["backups"].items():
        if restore_backup(backup_path, file_path):
            emit(f"♣ Restored {file_path} from {backup_path} after failed healing.")


def healing_agent(
    func: Callable[..., Any] = None, **local_config
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as original_error:
                return _run_sync(
                    _heal(func, args, kwargs, original_error, local_config, False)
                )

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as original_error:
                return await _heal(
                    func, args, kwargs, original_error, local_config, True
                )

        # An async function returns its coroutine before the body runs, so a
        # synchronous wrapper never sees the exception and never heals it.
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    if func is None:
        return decorator
    return decorator(func)


async def _invoke(target: Callable[..., Any], args: tuple, kwargs: dict, awaiting: bool):
    """Call back into the user's code, awaiting the result when appropriate.

    `awaiting` says the decorated function was a coroutine function, but the
    check stays on the RESULT: a candidate repair is generated text, and a
    model that answers an `async def` with a plain `def` would otherwise turn
    a working repair into "object is not awaitable".
    """
    result = target(*args, **kwargs)
    if awaiting and inspect.isawaitable(result):
        result = await result
    return result


def _run_sync(coro):
    """Run the healing session for a synchronous function.

    `_heal` is written once, as a coroutine, so the session bookkeeping is not
    duplicated for async callers. With ``awaiting=False`` it has no suspension
    points, so a single ``send(None)`` runs it to completion and the return
    value arrives on ``StopIteration``. Exceptions propagate untouched, which
    is what keeps the original error the one that reaches the application.

    Should a real ``await`` ever be introduced into the session, this fails
    loudly instead of silently returning a coroutine nobody awaits.
    """
    try:
        coro.send(None)
    except StopIteration as completed:
        return completed.value
    coro.close()
    raise RuntimeError(
        "the healing session suspended in a synchronous context; "
        "_heal must not await anything unless awaiting=True"
    )


async def _heal(
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    original_error: Exception,
    local_config: dict,
    awaiting: bool,
) -> Any:
    """Own one healing session and return the repaired result, or re-raise.

    Shared verbatim by the synchronous and asynchronous wrappers. Only the
    calls into the user's own code differ, and `awaiting` selects those; every
    other step - config, attempt budget, backup, apply, verify, restore,
    escalation - is identical and lives here exactly once.
    """
    # The outermost invocation owns the healing session and is the
    # only one allowed to restore sources, because repair attempts
    # nest through the reloaded, still-decorated function.
    session = _healing_session.get()
    session_token = None
    usage_token = None
    if session is None:
        session = {"backups": {}, "restore_enabled": True, "config": {}}
        session_token = _healing_session.set(session)
        # Token accounting is scoped to the same outermost session,
        # so one repair's cost covers every nested attempt it made.
        usage_token = usage_ledger.start()
    healed_successfully = False
    try:
        config, _ = load_config()
        config.update(local_config)
        if session_token is not None:
            session["restore_enabled"] = bool(
                config.get("RESTORE_ON_FAILURE", True)
            )
            session["config"] = config

        repair_key = _repair_key(func)
        attempts = _current_attempts()
        attempts_used = attempts.get(repair_key, 0)
        max_attempts = config.get("MAX_ATTEMPTS")
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts <= 0
        ):
            raise ValueError("MAX_ATTEMPTS must be a positive integer")

        if attempts_used >= max_attempts:
            emit(
                f"♣ Healing stopped after {max_attempts} repair "
                f"attempt(s) for {func.__qualname__}."
            )
            raise original_error

        next_attempts = dict(attempts)
        next_attempts[repair_key] = attempts_used + 1
        token = _repair_attempts.set(next_attempts)
        try:
            healed, result = await _attempt_healing(
                func,
                args,
                kwargs,
                original_error,
                config,
                attempts_used + 1,
                max_attempts,
                awaiting,
            )
            if healed:
                healed_successfully = True
                return result
        finally:
            _repair_attempts.reset(token)
    except Exception as healing_error:
        if healing_error is original_error:
            raise
        emit(f"♣ Healing failed: {healing_error}", level=logging.ERROR)
        raise original_error from healing_error
    finally:
        # A definitive failure must not leave a half-healed source
        # file behind; the candidate stays in _healing_agent_fixes/.
        if session_token is not None:
            if (session.get("config") or {}).get("DEBUG"):
                emit(f"♣ Model usage: {usage_ledger.describe()}")
            if not healed_successfully:
                if session["restore_enabled"]:
                    _restore_session_sources(session)
                # Plan B: escalate so the failure is not lost. The
                # helper is a no-op unless issue_on_failure is set,
                # and never raises over the application's error.
                if session.get("context") is not None:
                    open_issue_for_failure(
                        session["context"], session["config"]
                    )
            _healing_session.reset(session_token)
            usage_ledger.reset(usage_token)

    # AUTO_FIX=False, an invalid proposal, or an unavailable reload
    # must never turn an application failure into an implicit None.
    raise original_error


async def _attempt_healing(
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    error: Exception,
    config: dict,
    attempt_number: int,
    max_attempts: int,
    awaiting: bool = False,
) -> tuple[bool, Any]:
    """Try one repair and report whether a repaired result was produced.

    `awaiting` is True when the decorated function is a coroutine function, and
    selects whether the two calls back into the user's code are awaited.
    """
    import importlib.util
    import inspect
    import sys

    emit("\n")
    emit(
        f"♣ ⚕️⚕️⚕️  {'✧' * 25} HEALING AGENT STARTED "
        f"{'✧' * 25} ⚕️⚕️⚕️ ♣"
    )
    emit(f"♣ Repair attempt {attempt_number}/{max_attempts}")
    emit(f"♣ ⚕️  Error caught: {type(error).__name__} - {error}")

    context = capture_context(
        func=func,
        args=args,
        kwargs=kwargs,
        config=config,
        error=error,
    )

    # One chokepoint protects both provider submission and saved artifacts.
    context = redact(context, config)
    if config.get("DEBUG"):
        emit("♣ Context redacted for secrets before AI/disk usage")

    # A deliberate request carries intent an exception cannot: the program
    # states what it expected, not merely where it stopped.
    if isinstance(error, HealingRequested):
        context["healing_request"] = {
            "reason": error.reason,
            "details": error.details,
        }

    # Optional narrative: what the application was doing before it broke.
    recent_logs = recent_records(config)
    if recent_logs:
        context["recent_logs"] = recent_logs
    else:
        arm_from_config_if_requested(config)

    # Escalation should describe the original application failure, not a
    # later failure of the agent's own candidate.
    _register_failure_context(context)

    hint = generate_hint(context, config)
    context["ai_hint"] = hint

    emit(
        f"♣ In file: {context['error']['file']}, "
        f"line {context['error']['line_number']}"
    )
    emit(
        f"♣ Function name: {context['function_info']['name']}, "
        f"starting line: "
        f"{context['function_info']['starting_line_number']}"
    )
    emit(f"♣ Error message: {context['error']['error_line']}")
    emit(f"♣ The Agent's hint: {hint}")

    if config.get("DEBUG"):
        emit("\n♣ ⚕️  Detailed Error Information:")
        emit(f"♣ Error occurred in function: {context['error']['function_name']}")
        emit(f"♣ Error line: {context['error']['error_line']}")
        if "source_lines" in context["function_info"]:
            emit("♣ Source code captured successfully")

    fixed_code = fix(context, config)
    context["fixed_code"] = fixed_code

    if config.get("DEBUG") and fixed_code:
        emit("♣ Successfully generated fixed code")

    if config.get("SAVE_AI_FIXES", True) and fixed_code:
        saved_fix = save_ai_fix(context)
        if config.get("DEBUG"):
            emit(f"♣ AI fix saved to: {saved_fix}")

    git_mode = config.get("GIT_MODE", "off")
    if config.get("SAVE_GIT_PATCHES", False) and git_mode == "off":
        # Preserve the 0.2.8 flag while making the richer mode explicit.
        git_mode = "patch"

    if git_mode != "off" and fixed_code:
        context["git_patch_dir"] = config.get("GIT_PATCH_DIR")
        saved_patch = save_git_patch(context)
        context["git_patch_path"] = saved_patch
        if config.get("DEBUG"):
            emit(f"♣ Reviewable Git patch saved to: {saved_patch}")

    if config.get("SAVE_EXCEPTIONS"):
        saved_context = save_context(context)
        if config.get("DEBUG"):
            emit(f"♣ Exception details saved to: {saved_context}")

    if isinstance(error, (ImportError, ModuleNotFoundError)) and config.get(
        "AUTO_SYSCHANGE", False
    ):
        if install_missing_module(str(error), config.get("DEBUG", False)):
            emit(f"♣ Successfully installed missing module: {error}")
            return True, await _invoke(func, args, kwargs, awaiting)

    if not config.get("AUTO_FIX", True) or not fixed_code:
        return False, None

    if config.get("DEBUG"):
        emit(f"♣ Attempting to update file: {context['error']['file']}")
        emit(f"♣ Replacing function: {context['error']['function_name']}")

    if not verify_candidate(context, fixed_code, config):
        return False, None

    if config.get("BACKUP_ENABLED", True):
        saved_backup = create_backup(context)
        context["backup_path"] = saved_backup
        # Only the first backup per file is kept: it holds the pre-healing
        # source that a failed session must be restored to.
        _register_backup(context["error"]["file"], saved_backup)
        if config.get("DEBUG"):
            emit(f"♣ Created backup in backup folder: {saved_backup}")

    if git_mode == "apply":
        if not context.get("git_patch_path"):
            emit("♣ Git patch was not generated or did not pass git apply --check.")
            return False, None
        try:
            apply_git_patch(
                context["git_patch_path"],
                stage=bool(config.get("GIT_STAGE", False)),
            )
        except Exception as git_error:
            emit(f"♣ Git refused the candidate patch: {git_error}", level=logging.ERROR)
            return False, None
    elif not function_replacer(context, fixed_code):
        emit("♣ Generated fix could not be applied.", level=logging.ERROR)
        return False, None

    module_name = func.__module__
    if module_name not in sys.modules:
        emit(f"♣ Module {module_name} is not loaded; cannot verify the repair.")
        return False, None

    module = sys.modules[module_name]
    module_file = inspect.getfile(module)
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not find a loader for module {module_name} at {module_file}"
        )

    new_module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = new_module
    try:
        spec.loader.exec_module(new_module)
        updated_func = getattr(new_module, func.__name__)
        result = await _invoke(updated_func, args, kwargs, awaiting)
    except Exception:
        # Do not leave a partially loaded or still-failing repaired module in
        # sys.modules. The source backup remains available for explicit rollback.
        sys.modules[module_name] = module
        raise
    emit("♣ Fixed code executed with original arguments.")
    emit(
        f"♣ ⚕️⚕️⚕️  {'✧' * 25} HEALING AGENT FINISHED "
        f"{'✧' * 25} ⚕️⚕️⚕️  ♣\n"
    )
    return True, result
