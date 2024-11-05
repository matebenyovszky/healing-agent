import json
import datetime
import traceback
import inspect
import sys
import ast
from typing import Optional, Any, Dict, Callable
import requests

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
    """
    # First try to get source directly from file
    if hasattr(func, '__code__') and hasattr(func.__code__, 'co_filename'):
        file_path = func.__code__.co_filename
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
            
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func.__name__:
                start_line = node.lineno
                end_line = node.end_lineno
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    source_lines = all_lines[start_line-1:end_line]
                    return source_lines, start_line
                    
    # Fallback to inspect
    return inspect.getsourcelines(func)

def handle_exception(
    error: Exception,
    func: Optional[Callable] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
    config: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Captures execution context and saves exception details to a file.
    
    Args:
        error: The caught exception
        func: Optional function object that raised the exception
        args: Optional positional arguments passed to the function
        kwargs: Optional keyword arguments passed to the function
        json_details: Optional dictionary containing JSON-related error details
        
    Returns:
        dict: The captured context
    """

    # Reset/initialize important variables
    caller_frame = None
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
    }

    # Get the frame of the caller
    caller_frame = inspect.currentframe().f_back

    # Get exception info early
    exc_type, exc_value, exc_traceback = sys.exc_info()
    trace = traceback.extract_tb(exc_traceback)

    # Find the frame where the actual error occurred
    error_frame = None
    for frame in reversed(trace):
        if func and frame.filename == inspect.getfile(func):
            error_frame = frame
            break
    
    # If we couldn't find the frame in the function, use the last frame
    if not error_frame:
        error_frame = trace[-1]

    # Capture global and local variables from the error frame
    if error_frame:
        frame_obj = None
        tb = exc_traceback
        while tb:
            if tb.tb_frame.f_code.co_filename == error_frame.filename and tb.tb_frame.f_lineno == error_frame.lineno:
                frame_obj = tb.tb_frame
                break
            tb = tb.tb_next

        if frame_obj:
            # Capture local variables
            local_vars = {}
            for key, value in frame_obj.f_locals.items():
                try:
                    var_str = str(value)[:200]  # Limit to first 200 chars
                    local_vars[key] = {
                        'type': type(value).__name__,
                        'value_preview': var_str
                    }
                except:
                    local_vars[key] = {
                        'type': type(value).__name__,
                        'value_preview': '<Error converting to string>'
                    }

            # Capture global variables
            global_vars = {}
            for key, value in frame_obj.f_globals.items():
                if not key.startswith('__'):  # Skip built-ins and private vars
                    try:
                        var_str = str(value)[:200]  # Limit to first 200 chars
                        global_vars[key] = {
                            'type': type(value).__name__,
                            'value_preview': var_str
                        }
                    except:
                        global_vars[key] = {
                            'type': type(value).__name__,
                            'value_preview': '<Error converting to string>'
                        }

            context['variables'] = {
                'locals': local_vars,
                'globals': global_vars
            }
    
    # Enhanced error context with safe attribute access
    error_details = {
        'type': type(error).__name__,
        'message': str(error),
        'traceback': traceback.format_exc(),
        'attributes': {}
    }
    
    # Replace the attribute collection logic with safer version
    for attr in dir(error):
        if not attr.startswith('_'):
            try:
                value = getattr(error, attr)
                if not callable(value):
                    # Safely convert the value to a serializable format
                    if isinstance(value, (str, int, float, bool, type(None))):
                        error_details['attributes'][attr] = value
                    else:
                        # For objects that might not be JSON serializable
                        error_details['attributes'][attr] = safe_str(value)
            except Exception as e:
                # Log the problematic attribute but continue processing
                error_details['attributes'][attr] = f"<Error accessing attribute: {str(e)}>"

    context['error'] = {
        'type': exc_type.__name__,
        'message': str(exc_value),
        'traceback': traceback.format_exc(),
        'line_number': error_frame.lineno if error_frame else None,
        'file': error_frame.filename if error_frame else None,
        'function_name': error_frame.name if error_frame else None,
        'error_line': error_frame.line if error_frame else None,
        'exception_attrs': error_details['attributes']
    }

    # Add full traceback information for debugging
    context['error']['traceback_frames'] = [{
        'filename': frame.filename,
        'line_number': frame.lineno,
        'function': frame.name,
        'code': frame.line
    } for frame in trace]

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
    
    elif isinstance(error, ValueError):
        context['error']['value_details'] = {'args': error.args}
    
    elif isinstance(error, KeyError):
        context['error']['key_details'] = {'args': error.args}
    
    elif isinstance(error, TypeError):
        context['error']['type_details'] = {'args': error.args}
    
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

    # Enhance function_info with both sets of argument data
    if func:
        try:
            # Get source code using AST
            try:
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

                source_verification = 'PASSED' if func.__name__ in source_code else 'FAILED'
                context['function_info'] = {
                    'name': func.__name__,
                    'qualname': func.__qualname__,
                    'module': func.__module__,
                    'filename': inspect.getfile(func),
                    'starting_line_number': start_line,
                    'source_code': source_code.strip(),
                    'signature': str(sig),
                    'source_lines': {
                        i + start_line: line.rstrip()
                        for i, line in enumerate(source_lines)
                    },
                    'source_verification': source_verification
                }

            except Exception as source_error:
                print(f"♣ Warning: Failed to capture source code: {str(source_error)}")
                # Fallback to basic function info
                context['function_info'] = {
                    'name': func.__name__,
                    'qualname': func.__qualname__,
                    'module': func.__module__,
                    'filename': inspect.getfile(func),
                    'source_error': str(source_error)
                }

            context['function_arguments'] = arguments_info

        except Exception as e:
            context['function_info'] = {
                'note': f'Failed to capture function details: {str(e)}',
                'error_traceback': traceback.format_exc()
            }
    
    return context
