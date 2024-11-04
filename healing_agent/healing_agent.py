from functools import wraps
from typing import Callable, Any

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
                # Execute the function with minimal overhead
                return func(*args, **kwargs)
            except Exception as e:
                # Lazy load imports only when exception occurs

                print(f"♣ ⚕️⚕️⚕️  {'✧'*25} HEALING AGENT STARTED {'✧'*25} ⚕️⚕️⚕️ ♣")
                print(f"♣ ⚕️ Error caught: {type(e).__name__} - {str(e)}")

                import inspect
                import sys
                import importlib.util
                
                # Load config only when an exception occurs
                config = load_config()
                # Merge local configuration overrides
                config.update(local_config)

                # Handle the exception
                context = handle_exception(
                    error=e,
                    func=func,
                    args=args,
                    kwargs=kwargs,
                    config=config
                )
                
                # Generate AI hint for the exception
                hint = generate_hint(context, config)
                context['ai_hint'] = hint
                
                # Print detailed error information


                print(f"♣ In file: {context['error']['file']}, line {context['error']['line_number']}")
                print(f"♣ Function name: {context['function_info']['name']}, starting line: {context['function_info']['starting_line_number']}")
                print(f"♣ Error message: {context['error']['error_line']}")
                print(f"♣ The Agent's hint: {hint}")

                
                # Add after context creation
                if config.get('DEBUG'):
                    print("\n♣ ⚕️ Detailed Error Information:")
                    print(f"♣ Error occurred in function: {context['error']['function_name']}")
                    print(f"♣ Error line: {context['error']['error_line']}")
                    print(f"♣ Source verification: {context['function_info']['source_verification']}")
                    if 'source_lines' in context['function_info']:
                        print("♣ Source code captured successfully")
                
                # Fix the code
                fixed_code = fix(context, config)
                context['fixed_code'] = fixed_code

                if config.get('DEBUG', False) and fixed_code:
                    print("♣ Successfully generated fixed code")

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
                
                print(f"♣ ⚕️⚕️⚕️  {'✧'*25} HEALING AGENT FINISHED {'✧'*25} ⚕️⚕️⚕️ ♣")
                return

        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)
