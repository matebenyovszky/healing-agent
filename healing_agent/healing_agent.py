import inspect
from functools import wraps
from typing import Callable, Any
import sys
import requests
import importlib.util

from .exception_handler import handle_exception
from .ai_code_fixer import fix
from .ai_hint_generator import generate_hint
from .config_loader import load_config
from .code_backup import create_backup
from .code_replacer import function_replacer
from .exception_saver import save_context



def healing_agent(func: Callable[..., Any] = None, **local_config) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # Execute the function
                result = func(*args, **kwargs)
                return result
                
            except Exception as e:
                
                # Load the global configuration
                config = load_config()
                
                # Merge local configuration overrides
                config.update(local_config)

                # Handle the exception
                context = dict()
                context = handle_exception(
                    error=e,
                    func=func,
                    args=args,
                    kwargs=kwargs,
                    config=config
                )
                
                ### Question: Could I move these checks to the exception_handler.py?

                # Check if the exception is a JSONDecodeError
                if isinstance(e, requests.exceptions.JSONDecodeError):
                    # Extract first 1000 chars of JSON before handling exception
                    json_preview = e.doc[:1000] if hasattr(e, 'doc') and e.doc else None
                    context['error']['json_details'] = {'response_text': json_preview}
                
                # Check if the exception is a ConnectionError
                elif isinstance(e, requests.exceptions.ConnectionError):
                    # Add connection-specific details to the context
                    context['error']['connection_details'] = {
                        'request': e.request.__dict__ if e.request else None,
                        'response': e.response.__dict__ if e.response else None
                    }
                
                # Check if the exception is a Timeout
                elif isinstance(e, requests.exceptions.Timeout):
                    # Add timeout-specific details to the context
                    context['error']['timeout_details'] = {
                        'request': e.request.__dict__ if e.request else None,
                        'timeout': e.args[0] if e.args else None
                    }
                
                # Check if the exception is an HTTPError
                elif isinstance(e, requests.exceptions.HTTPError):
                    # Add HTTP-specific details to the context
                    context['error']['http_details'] = {
                        'request': e.request.__dict__ if e.request else None,
                        'response': e.response.__dict__ if e.response else None
                    }
                
                # Check if the exception is a ValueError
                elif isinstance(e, ValueError):
                    # Add value-specific details to the context
                    context['error']['value_details'] = {
                        'args': e.args
                    }
                
                # Check if the exception is a KeyError
                elif isinstance(e, KeyError):
                    # Add key-specific details to the context
                    context['error']['key_details'] = {
                        'args': e.args
                    }
                
                # Check if the exception is a TypeError
                elif isinstance(e, TypeError):
                    # Add type-specific details to the context
                    context['error']['type_details'] = {
                        'args': e.args
                    }
                
                # Check if the exception is a FileNotFoundError
                elif isinstance(e, FileNotFoundError):
                    # Add file-specific details to the context
                    context['error']['file_details'] = {
                        'filename': e.filename,
                        'errno': e.errno,
                        'strerror': e.strerror
                    }
                
                # For any other standard exception, add basic details
                else:
                    context['error']['details'] = {
                        'args': getattr(e, 'args', None),
                        'message': str(e)
                    }
                
                # Generate AI hint for the exception
                hint = generate_hint(context, config)
                context['ai_hint'] = hint
                
                # Print detailed error information
                print(f"♣ ⚕️  {'✧'*25} HEALING AGENT {'✧'*25} ⚕️  ♣")
                print(f"♣ Error caught: {context['error']['type']} - {context['error']['message']}")
                print(f"♣ In file: {context['error']['file']}, line {context['error']['line_number']}")
                print(f"♣ The Agent's hint: {hint}")
                print(f"♣ ⚕️  {'✧'*25} HEALING AGENT {'✧'*25} ⚕️  ♣")
                
                # Add after context creation
                if config.get('DEBUG'):
                    print("\nDetailed Error Information:")
                    print(f"♣ Error occurred in function: {context['error']['function_name']}")
                    print(f"♣ Error line: {context['error']['error_line']}")
                    print(f"♣ Source verification: {'PASSED' if func.__name__ in context['function_info']['source_code'] else 'FAILED'}")
                    print("♣ Source code:")
                    for line_no, line in context['function_info']['source_lines'].items():
                        print(f"  {line_no}: {line}")
                
                # Fix the code
                fixed_code = fix(context, config)
                context['fixed_code'] = fixed_code

                # Save the exception details
                if config.get('SAVE_EXCEPTIONS'):
                    saved_context = save_context(context)

                    if config.get('DEBUG'):
                        print(f"♣ Exception details saved to: {saved_context}")

                if config.get('AUTO_FIX', True):
                    # Create backup before modifications
                    if config.get('BACKUP_ENABLED', True):
                        saved_backup = create_backup(context)
                        context['backup_path'] = saved_backup

                        if config.get('DEBUG'):
                            print(f"♣ Created backup in backup folder: {saved_backup}")

                    # Replace the function in the file
                    if config.get('DEBUG'):
                        print(f"♣ Attempting to update file: {context['error']['file']}")
                        print(f"♣ Replacing function: {context['error']['function_name']}")
                    function_replacer(context, fixed_code)
                    if config.get('DEBUG'):
                        print(f"♣ Successfully updated {context['error']['file']}")

                    # Reload the module to get the updated code
                    module_name = func.__module__
                    if module_name in sys.modules:
                        try:
                            if config.get('DEBUG'):
                                print(f"♣ Reloading module: {module_name}")
                                
                            # Get the module object and its file path
                            module = sys.modules[module_name]
                            module_file = inspect.getfile(module)
                            
                            # Get the module specification
                            spec = importlib.util.spec_from_file_location(
                                module_name,
                                module_file
                            )
                                
                            if spec is None:
                                raise ImportError(f"Could not find spec for module {module_name} at {module_file}")
                                
                            # Create a new module based on the spec
                            new_module = importlib.util.module_from_spec(spec)
                            
                            # Add the new module to sys.modules
                            sys.modules[module_name] = new_module
                            
                            # Execute the module
                            spec.loader.exec_module(new_module)
                                
                            if config.get('DEBUG'):
                                print(f"♣ Successfully reloaded module from {module_file}")
                                
                            # Get the updated function
                            updated_func = getattr(new_module, func.__name__)
                                
                            if config.get('DEBUG'):
                                print(f"♣ Successfully retrieved function: {func.__name__}")
                                
                            # Execute the updated function with original arguments
                            result = updated_func(*args, **kwargs)
                            print(f"♣ Fixed code executed with original arguments.")
                            return result
                                
                        except Exception as reload_error:
                            print(f"♣ Warning: Failed to reload module: {str(reload_error)}")
                            if config.get('DEBUG'):
                                print(f"♣ Module details:")
                                print(f"  • Name: {module_name}")
                                print(f"  • File: {getattr(module, '__file__', 'Unknown')}")
                                print(f"  • Path: {getattr(module, '__path__', ['Unknown'])}")
                
                return None

        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)
