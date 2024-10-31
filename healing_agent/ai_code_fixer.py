import re
from typing import Dict, Any
from .ai_broker import get_ai_response

def ensure_healing_agent_decorator(code: str) -> str:
    """
    Ensures the code has the @healing_agent decorator, adds it if missing.
    
    Args:
        code (str): The code to check/modify
        
    Returns:
        str: Code with @healing_agent decorator
    """
    # Check the first 5 lines for the @healing_agent decorator
    lines = code.split('\n')[:5]
    for line in lines:
        if line.strip() == '@healing_agent':
            return code  # Decorator already present

    # If not found, add the decorator at the top
    first_line = code.split('\n')[0]
    indent = len(first_line) - len(first_line.lstrip())
    decorator = ' ' * indent + '@healing_agent\n'
    return decorator + code


def prepare_fix_prompt(context: Dict[str, Any]) -> str:
    """
    Prepare the prompt for AI based on the context.
    
    Args:
        context (Dict[str, Any]): The error context
        
    Returns:
        str: Formatted prompt for the AI
    """
    # Extract function info if available
    function_info = context.get('function_info', {})
    function_args = context.get('function_arguments', {})
    error_info = context.get('error', {})
    
    # Build argument info string
    arg_info = ""
    if function_args:
        arg_info = "\nFunction was called with arguments:\n"
        for arg_name, arg_data in function_args.items():
            arg_info += f"{arg_name}: {arg_data.get('value')} (type: {arg_data.get('type')})\n"
    
    # Build function info string
    func_info = ""
    if function_info:
        func_info = f"""
Function Name: {function_info.get('name')}
Function Signature: {function_info.get('signature')}
Module: {function_info.get('module')}
"""

    # Build error details string
    error_details = ""
    if error_info.get('exception_attrs'):
        error_details = "\nDetailed Error Information:\n"
        for attr, value in error_info['exception_attrs'].items():
            error_details += f"{attr}: {value}\n"

    # Add traceback frames for context
    traceback_info = ""
    if error_info.get('traceback_frames'):
        traceback_info = "\nTraceback Frames:\n"
        for frame in error_info['traceback_frames']:
            traceback_info += f"File: {frame['filename']}, Line {frame['line_number']}, in {frame['function']}\n"
            traceback_info += f"Code: {frame['code']}\n"

    # Include AI hint if available
    ai_hint = ""
    if context.get('ai_hint'):
        ai_hint = f"\nAI Analysis:\n{context['ai_hint']}"

    return f"""
Fix the following Python code that produced an error, or at least handle the exceptions, add more info that could help debugging next time:

Original Code:
{context['function_info']['source_code']}

Error Type: {context['error']['type']}
Error Message: {context['error']['message']}
Error Line Number: {context['error'].get('line_number')}
Error Line: {context['error'].get('error_line')}

{error_details}
{traceback_info}
{func_info}{arg_info}{ai_hint}

Return only the fixed code without any explanations or markdown formatting.
Ensure the fixed code maintains the same function name and signature.
Add appropriate error handling where necessary.
"""

def validate_fixed_code(fixed_code: str) -> bool:
    """
    Validate the fixed code is syntactically correct.
    
    Args:
        fixed_code (str): The code to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    try:
        # Check if the code is syntactically valid Python
        compile(fixed_code, '<string>', 'exec')
        
        # Basic checks for common issues
        if not fixed_code.strip():
            print("♣ Generated code is empty")
            return False
            
        if "def " not in fixed_code:
            print("♣ Generated code doesn't contain function definition")
            return False
            
        return True
        
    except SyntaxError as e:
        print(f"♣ Syntax error in generated code: {str(e)}")
        return False
    except Exception as e:
        print(f"♣ Validation error: {str(e)}")
        return False

def fix(context: Dict[str, Any], config: Dict[str, Any]) -> str:
    """
    Fix buggy code using AI based on the provided context.
    
    Args:
        context (Dict[str, Any]): Dictionary containing:
            - original_code (str): The original buggy code
            - error_info (Dict): Error details including type, message, traceback
            - stack_trace (str): Full stack trace of the error
            - function_name (str): Name of the function that caused the error
            - additional_context (Dict): Any additional context that might help
    
    Returns:
        str: The fixed version of the code
    """
    try:
        # Prepare the prompt for AI
        prompt = prepare_fix_prompt(context)
        
        # Get the fix from AI with code_fixer role
        fixed_code = get_ai_response(prompt, config, "code_fixer")

        # Remove markdown code block formatting if present
        fixed_code = re.sub(r'^```python\n|^```\n|```$', '', fixed_code, flags=re.MULTILINE)
        
        # Ensure healing_agent decorator is present
        fixed_code = ensure_healing_agent_decorator(fixed_code)
        
        # Validate the fixed code
        if validate_fixed_code(fixed_code):
            if config.get('DEBUG', False):
                print("♣ Successfully generated fixed code")
                print(f"♣ Fixed code: {fixed_code}")
            return fixed_code
        else:
            print("♣ Generated fix failed validation")
            return

    except Exception as e:
        print(f"♣ Error during code fixing: {str(e)}")
        print(f"♣ Error type: {type(e).__name__}")
        print(f"♣ Error details: {repr(e)}")
        print(f"♣ Error traceback:")
        import traceback
        traceback.print_exc()
        return
