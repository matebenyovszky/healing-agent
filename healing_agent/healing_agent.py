import inspect
from functools import wraps
from typing import Callable, Any
import sys
from .exception_handler import handle_exception
from .code_fixer import fix
from .load_config import load_config
from .create_backup import create_backup
from .code_replacer import function_replacer
import importlib
import importlib.util
import traceback
import os

def healing_agent(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that catches exceptions and captures detailed execution context.
    """
    config = load_config()
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # Execute the function
            result = func(*args, **kwargs)
            return result
            
        except Exception as e:
            # Handle exception with full context
            context = handle_exception(
                error=e,
                func=func,
                args=args,
                kwargs=kwargs,
                config=config
            )
            
            # Fix the code
            fixed_code = fix(context, config)

            if config.get('AUTO_FIX', True):
                # Create backup before modifications
                if config.get('BACKUP_ENABLED', True):
                    source_file = context['error']['file']
                    create_backup(source_file, config)

                # Replace the function in the file
                function_replacer(context, fixed_code, config)

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
                            print(f"♣ Reload error traceback: {traceback.format_exc()}")
                            print(f"♣ Module details:")
                            print(f"  • Name: {module_name}")
                            print(f"  • File: {getattr(module, '__file__', 'Unknown')}")
                            print(f"  • Path: {getattr(module, '__path__', ['Unknown'])}")
            
            # If we get here, either auto-fix is disabled or reload failed
            return None
            
    return wrapper
