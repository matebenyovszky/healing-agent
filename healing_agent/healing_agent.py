from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Dict

from .agent_tools.tool_install_missing_module import install_missing_module
from .ai_code_fixer import fix
from .ai_fix_saver import save_ai_fix
from .ai_hint_generator import generate_hint
from .code_backup import create_backup
from .code_replacer import function_replacer
from .config_loader import load_config
from .exception_handler import capture_context
from .exception_saver import save_context
from .git_patch_saver import save_git_patch
from .redactor import redact


_repair_attempts: ContextVar[Dict[str, int]] = ContextVar(
    "healing_agent_repair_attempts", default={}
)


def _repair_key(func: Callable[..., Any]) -> str:
    """Return a stable key across reloads of the decorated function."""
    return f"{func.__module__}:{func.__qualname__}"


def healing_agent(
    func: Callable[..., Any] = None, **local_config
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as original_error:
                try:
                    config, _ = load_config()
                    config.update(local_config)

                    repair_key = _repair_key(func)
                    attempts = _repair_attempts.get()
                    attempts_used = attempts.get(repair_key, 0)
                    max_attempts = config.get("MAX_ATTEMPTS")
                    if (
                        isinstance(max_attempts, bool)
                        or not isinstance(max_attempts, int)
                        or max_attempts <= 0
                    ):
                        raise ValueError("MAX_ATTEMPTS must be a positive integer")

                    if attempts_used >= max_attempts:
                        print(
                            f"♣ Healing stopped after {max_attempts} repair "
                            f"attempt(s) for {func.__qualname__}."
                        )
                        raise original_error

                    next_attempts = dict(attempts)
                    next_attempts[repair_key] = attempts_used + 1
                    token = _repair_attempts.set(next_attempts)
                    try:
                        healed, result = _attempt_healing(
                            func,
                            args,
                            kwargs,
                            original_error,
                            config,
                            attempts_used + 1,
                            max_attempts,
                        )
                        if healed:
                            return result
                    finally:
                        _repair_attempts.reset(token)
                except Exception as healing_error:
                    if healing_error is original_error:
                        raise
                    print(f"♣ Healing failed: {healing_error}")
                    raise original_error from healing_error

                # AUTO_FIX=False, an invalid proposal, or an unavailable reload
                # must never turn an application failure into an implicit None.
                raise

        return wrapper

    if func is None:
        return decorator
    return decorator(func)


def _attempt_healing(
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    error: Exception,
    config: dict,
    attempt_number: int,
    max_attempts: int,
) -> tuple[bool, Any]:
    """Try one repair and report whether a repaired result was produced."""
    import importlib.util
    import inspect
    import sys

    print("\n")
    print(
        f"♣ ⚕️⚕️⚕️  {'✧' * 25} HEALING AGENT STARTED "
        f"{'✧' * 25} ⚕️⚕️⚕️ ♣"
    )
    print(f"♣ Repair attempt {attempt_number}/{max_attempts}")
    print(f"♣ ⚕️  Error caught: {type(error).__name__} - {error}")

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
        print("♣ Context redacted for secrets before AI/disk usage")

    hint = generate_hint(context, config)
    context["ai_hint"] = hint

    print(
        f"♣ In file: {context['error']['file']}, "
        f"line {context['error']['line_number']}"
    )
    print(
        f"♣ Function name: {context['function_info']['name']}, "
        f"starting line: "
        f"{context['function_info']['starting_line_number']}"
    )
    print(f"♣ Error message: {context['error']['error_line']}")
    print(f"♣ The Agent's hint: {hint}")

    if config.get("DEBUG"):
        print("\n♣ ⚕️  Detailed Error Information:")
        print(f"♣ Error occurred in function: {context['error']['function_name']}")
        print(f"♣ Error line: {context['error']['error_line']}")
        if "source_lines" in context["function_info"]:
            print("♣ Source code captured successfully")

    fixed_code = fix(context, config)
    context["fixed_code"] = fixed_code

    if config.get("DEBUG") and fixed_code:
        print("♣ Successfully generated fixed code")

    if config.get("SAVE_AI_FIXES", True) and fixed_code:
        saved_fix = save_ai_fix(context)
        if config.get("DEBUG"):
            print(f"♣ AI fix saved to: {saved_fix}")

    if config.get("SAVE_GIT_PATCHES", False) and fixed_code:
        saved_patch = save_git_patch(context)
        context["git_patch_path"] = saved_patch
        if config.get("DEBUG"):
            print(f"♣ Reviewable Git patch saved to: {saved_patch}")

    if config.get("SAVE_EXCEPTIONS"):
        saved_context = save_context(context)
        if config.get("DEBUG"):
            print(f"♣ Exception details saved to: {saved_context}")

    if isinstance(error, (ImportError, ModuleNotFoundError)) and config.get(
        "AUTO_SYSCHANGE", False
    ):
        if install_missing_module(str(error), config.get("DEBUG", False)):
            print(f"♣ Successfully installed missing module: {error}")
            return True, func(*args, **kwargs)

    if not config.get("AUTO_FIX", True) or not fixed_code:
        return False, None

    if config.get("BACKUP_ENABLED", True):
        saved_backup = create_backup(context)
        context["backup_path"] = saved_backup
        if config.get("DEBUG"):
            print(f"♣ Created backup in backup folder: {saved_backup}")

    if config.get("DEBUG"):
        print(f"♣ Attempting to update file: {context['error']['file']}")
        print(f"♣ Replacing function: {context['error']['function_name']}")

    if not function_replacer(context, fixed_code):
        print("♣ Generated fix could not be applied.")
        return False, None

    module_name = func.__module__
    if module_name not in sys.modules:
        print(f"♣ Module {module_name} is not loaded; cannot verify the repair.")
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
        result = updated_func(*args, **kwargs)
    except Exception:
        # Do not leave a partially loaded or still-failing repaired module in
        # sys.modules. The source backup remains available for explicit rollback.
        sys.modules[module_name] = module
        raise
    print("♣ Fixed code executed with original arguments.")
    print(
        f"♣ ⚕️⚕️⚕️  {'✧' * 25} HEALING AGENT FINISHED "
        f"{'✧' * 25} ⚕️⚕️⚕️  ♣\n"
    )
    return True, result
