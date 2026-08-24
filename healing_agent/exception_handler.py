import json
import datetime
import traceback
import inspect
import os
import sys
import ast
import textwrap
from typing import Optional, Any, Dict, Callable
import requests

from .code_replacer import find_function_node
from .redactor import (
    DEFAULT_PLACEHOLDER,
    get_sensitive_matcher,
    is_sensitive_name,
    scrub_value,
)

# Healing-agent's own wrapper-frame variables. In production, capture_context
# runs inside the decorator wrapper, so its caller frame holds these internals
# rather than the user's own state. `config` carries the provider API keys and
# `args`/`kwargs` duplicate (un-redacted) the user's call arguments, so they are
# never worth capturing and must never be serialized/sent.
_INTERNAL_SKIP_VARS = {
    'config', 'config_path', 'local_config', 'args', 'kwargs',
    'local_vars', 'global_vars', 'context',
}

def safe_str(obj: Any) -> str:
    """
    Safely convert any object to a string representation.
    """
    try:
        return str(obj)
    except Exception:
        return f"<Unprintable {type(obj).__name__} object>"

def get_function_source(func: Callable) -> tuple[list[str], int]:
    """
    Get function source code using AST and inspect.
    Returns tuple of (source_lines, start_line).

    The definition is located by ``__qualname__``, so a method is not confused
    with a module-level function of the same name, and ``async def`` is found
    like ``def`` — matching on the bare name missed both.
    """
    file_path = getattr(getattr(func, '__code__', None), 'co_filename', None)
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            node = find_function_node(
                ast.parse(source),
                getattr(func, '__qualname__', None),
                getattr(func, '__name__', None),
            )
            if node is not None:
                all_lines = source.splitlines(keepends=True)
                return all_lines[node.lineno - 1:node.end_lineno], node.lineno
        except (OSError, SyntaxError, ValueError):
            pass  # fall through to inspect, which has its own strategies

    # Fallback to inspect
    return inspect.getsourcelines(func)

#: Per-value capture limit. Generous, because the artifact on disk is meant to
#: be searchable later; what reaches a prompt or an issue is trimmed further at
#: render time by PROMPT_VALUE_CHARS.
DEFAULT_VALUE_CHARS = 3000


def _value_limit(config: Optional[dict] = None) -> int:
    try:
        limit = int((config or {}).get("CAPTURE_VALUE_CHARS", DEFAULT_VALUE_CHARS))
    except (TypeError, ValueError):
        return DEFAULT_VALUE_CHARS
    return limit if limit > 0 else DEFAULT_VALUE_CHARS


def trim_values(obj: Any, limit: int, _depth: int = 0) -> Any:
    """Return a copy of ``obj`` with every string trimmed to ``limit``.

    Used on the way out, so the same captured context can be rich on disk and
    affordable in a prompt without capturing it twice.
    """
    if _depth > 25:
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= limit else obj[:limit] + " …"
    if isinstance(obj, dict):
        return {key: trim_values(value, limit, _depth + 1) for key, value in obj.items()}
    if isinstance(obj, list):
        return [trim_values(value, limit, _depth + 1) for value in obj]
    if isinstance(obj, tuple):
        return tuple(trim_values(value, limit, _depth + 1) for value in obj)
    return obj


def capture_environment(config: Optional[dict] = None) -> Dict[str, Any]:
    """Capture the process environment, redacted by name AND by value.

    Which environment a failure happened in is often the whole diagnosis: a
    different deployment, a different locale, a feature flag that is set here
    and not there. It is also the most secret-dense structure in a process, so
    two filters apply rather than one — the usual name matching, plus value
    scrubbing for the secrets that hide under harmless names (`DATABASE_URL`
    carries a password inside a URL, `SENTRY_DSN` embeds a key).

    Every NAME is kept even when its value is masked: knowing that
    `AWS_SECRET_ACCESS_KEY` is set, or that a feature flag exists at all, is
    itself diagnostic.
    """
    matcher = get_sensitive_matcher(config)
    placeholder = (config or {}).get("REDACT_PLACEHOLDER") or DEFAULT_PLACEHOLDER
    limit = _value_limit(config)

    environment = {}
    for name, value in os.environ.items():
        if is_sensitive_name(name, matcher):
            environment[name] = placeholder
            continue
        try:
            scrubbed = scrub_value(value, placeholder)
        except Exception:
            scrubbed = placeholder
        environment[name] = scrubbed[:limit] if isinstance(scrubbed, str) else scrubbed
    return environment


def capture_context(
    func: Optional[Callable] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
    config: Optional[dict] = None,
    error: Optional[Exception] = None,
    frame: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Captures execution context with or without an exception.
    
    Args:
        func: Optional function object to capture context from
        args: Optional positional arguments passed to the function
        kwargs: Optional keyword arguments passed to the function
        config: Optional configuration dictionary
        error: Optional exception if capturing error context
        
    Returns:
        dict: The captured context
    """

    # Reset/initialize important variables
    exc_type = None
    exc_value = None
    exc_traceback = None
    trace = None
    error_frame = None
    context = dict()  # Explicitly reset context to empty dictionary

    # Capture enhanced context
    context = {
        'timestamp': datetime.datetime.now().isoformat(),
        'python_version': sys.version,
        'platform': sys.platform,
        'capture_type': 'error' if error else 'debug'
    }

    # Which environment the failure happened in is often the whole diagnosis.
    # Captured with both filters applied; see capture_environment.
    from .evidence import wanted_anywhere

    if wanted_anywhere(config, 'environment'):
        try:
            context['environment'] = capture_environment(config)
        except Exception as environment_error:
            context['environment'] = {
                'note': f'Failed to capture environment: {environment_error}'
            }

    # Capture function context if provided
    if func:
        try:
            # Get source code using AST
            source_lines, start_line = get_function_source(func)
            source_code = ''.join(source_lines)
            
            # Get the signature
            sig = inspect.signature(func)
            
            # Collect argument information
            arguments_info = {
                k: {
                    'value': str(v),
                    'type': str(type(v).__name__)
                } 
                for k, v in inspect.getcallargs(func, *(args or []), **(kwargs or {})).items()
            }

            context['function_info'] = {
                'name': func.__name__,
                'qualname': func.__qualname__,
                'module': func.__module__,
                'filename': inspect.getfile(func),
                'starting_line_number': start_line,
                # A method's source is indented at its class's column, so
                # `.strip()` alone left the first line at column zero and the
                # body indented - code the model cannot even parse.
                'source_code': textwrap.dedent(source_code).strip(),
                'signature': str(sig),
                'source_lines': {
                    i + start_line: line.rstrip()
                    for i, line in enumerate(source_lines)
                }
            }
            
            context['function_arguments'] = arguments_info

        except Exception as e:
            context['function_info'] = {
                'note': f'Failed to capture function details: {str(e)}',
                'error_traceback': traceback.format_exc()
            }

    # Capture frame information. An explicit frame lets a caller that is not
    # the decorator itself (e.g. the public capture() entry point) point at
    # the frame it actually wants to snapshot.
    if frame is None:
        frame = inspect.currentframe().f_back
    if frame:
        # Matcher for name-based secret redaction of variable previews.
        _matcher = get_sensitive_matcher(config)
        _limit = _value_limit(config)

        def _preview(key, value):
            """Build a {type, value_preview} entry, redacting sensitive names."""
            type_name = type(value).__name__
            if is_sensitive_name(key, _matcher):
                return {'type': type_name, 'value_preview': DEFAULT_PLACEHOLDER}
            try:
                var_str = str(value)[:_limit]
            except Exception:
                var_str = '<Error converting to string>'
            return {'type': type_name, 'value_preview': var_str}

        # Capture local variables (skip healing-agent internals that carry
        # credentials or duplicate the user's arguments).
        local_vars = {
            key: _preview(key, value)
            for key, value in frame.f_locals.items()
            if key not in _INTERNAL_SKIP_VARS
        }

        # Capture global variables (skip built-ins/private and internals).
        global_vars = {
            key: _preview(key, value)
            for key, value in frame.f_globals.items()
            if not key.startswith('__') and key not in _INTERNAL_SKIP_VARS
        }

        context['variables'] = {
            'locals': local_vars,
            'globals': global_vars
        }

    # If there's an error, add error-specific information
    if error:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        trace = traceback.extract_tb(exc_traceback)

        # Find the error frame
        error_frame = None
        for frame in reversed(trace):
            if func and frame.filename == inspect.getfile(func):
                error_frame = frame
                break
        
        if not error_frame and trace:
            error_frame = trace[-1]

        # Enhanced error context with safe attribute access
        error_details = {
            'type': type(error).__name__,
            'message': str(error),
            'traceback': traceback.format_exc(),
            'attributes': {}
        }
        
        # Collect error attributes safely
        for attr in dir(error):
            if not attr.startswith('_'):
                try:
                    value = getattr(error, attr)
                    if not callable(value):
                        if isinstance(value, (str, int, float, bool, type(None))):
                            error_details['attributes'][attr] = value
                        else:
                            error_details['attributes'][attr] = safe_str(value)
                except Exception as e:
                    error_details['attributes'][attr] = f"<Error accessing attribute: {str(e)}>"

        context['error'] = {
            'type': exc_type.__name__,
            'message': str(exc_value),
            'traceback': traceback.format_exc(),
            'line_number': error_frame.lineno if error_frame else None,
            'file': error_frame.filename if error_frame else None,
            'function_name': error_frame.name if error_frame else None,
            'error_line': error_frame.line if error_frame else None,
            'exception_attrs': error_details['attributes'],
            'traceback_frames': [{
                'filename': frame.filename,
                'line_number': frame.lineno,
                'function': frame.name,
                'code': frame.line
            } for frame in trace]
        }

        # Add exception-specific details
        if isinstance(error, json.JSONDecodeError):
            json_preview = error.doc[:1000] if hasattr(error, 'doc') and error.doc else None
            context['error']['json_details'] = {'response_text': json_preview}
        
        elif isinstance(error, requests.exceptions.ConnectionError):
            context['error']['connection_details'] = {
                'request': error.request.__dict__ if error.request else None,
                'response': error.response.__dict__ if error.response else None
            }
        
        elif isinstance(error, requests.exceptions.Timeout):
            context['error']['timeout_details'] = {
                'request': error.request.__dict__ if error.request else None,
                'timeout': error.args[0] if error.args else None
            }
        
        elif isinstance(error, requests.exceptions.HTTPError):
            try:
                context['error']['http_details'] = {
                    'request': {
                        'method': str(error.request.method) if error.request else None,
                        'url': str(error.request.url) if error.request else None,
                        'headers': {k: str(v) for k,v in error.request.headers.items()} if error.request and error.request.headers else None,
                        'body': str(error.request.body)[:1000] if error.request and error.request.body else None
                    } if error.request else None,
                    'response': {
                        'status_code': error.response.status_code if error.response else None,
                        'reason': str(error.response.reason) if error.response else None,
                        'headers': {k: str(v) for k,v in error.response.headers.items()} if error.response and error.response.headers else None,
                        'text': str(error.response.text)[:1000] if error.response and hasattr(error.response, 'text') else None
                    } if error.response else None
                }
            except Exception as json_err:
                context['error']['http_details'] = {
                    'error': f'Failed to serialize HTTP details: {str(json_err)}',
                    'status_code': error.response.status_code if error.response else None,
                    'url': str(error.request.url) if error.request else None
                }
        
        elif isinstance(error, (ValueError, KeyError, TypeError)):
            context['error'][f'{type(error).__name__.lower()}_details'] = {'args': error.args}
        
        elif isinstance(error, FileNotFoundError):
            context['error']['file_details'] = {
                'filename': error.filename,
                'errno': error.errno,
                'strerror': error.strerror
            }
        
        else:
            context['error']['details'] = {
                'args': getattr(error, 'args', None),
                'message': str(error)
            }

    return context
