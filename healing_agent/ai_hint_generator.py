from typing import Dict, Any
from .ai_broker import get_ai_response

def generate_hint(context: Dict[str, Any], config: Dict[str, Any]) -> str:
    """
    Generate an AI-powered hint based on the exception context.
    
    Args:
        context (Dict[str, Any]): The exception context
        config (Dict[str, Any]): The configuration dictionary
        
    Returns:
        str: The generated AI hint
    """
    # Extract error information
    error = context['error']
    error_type = error['type']
    error_message = error['message']
    function_name = error['function_name']
    traceback = error['traceback']
    traceback_frames = error['traceback_frames']
    exception_attrs = error['exception_attrs']
    
    # Extract any additional error details if present
    error_details = ""
    for detail_type in ['json_details', 'connection_details', 'timeout_details', 
                       'http_details', 'value_details', 'key_details', 
                       'type_details', 'file_details']:
        if detail_type in error:
            error_details += f"\n{detail_type}:\n{error[detail_type]}"
    
    # Get function info
    function_info = context.get('function_info', {})
    function_source = function_info.get('source_code', '')
    function_module = function_info.get('module', '')
    
    # Get function arguments. Render them explicitly rather than dumping the
    # capture structure: `{'payload': {'value': ..., 'type': 'dict'}}` invites
    # the model to read the wrapper keys ('value', 'type') as the argument's
    # OWN keys, which it has been observed to do.
    arguments = context.get('function_arguments', {})
    if isinstance(arguments, dict) and arguments:
        function_arguments = "\n".join(
            f"- {name} (type: {data.get('type')}) = {data.get('value')}"
            if isinstance(data, dict) else f"- {name} = {data}"
            for name, data in arguments.items()
        )
    else:
        function_arguments = "(none captured)"
    
    # Get environment info
    python_version = context.get('python_version', '')
    platform = context.get('platform', '')

    # What the application was doing before it broke (only when log capture
    # is armed; see healing_agent.enable_log_capture).
    recent_logs = ""
    if context.get('recent_logs'):
        joined = "\n".join(str(line) for line in context['recent_logs'])
        recent_logs = f"\nApplication log records leading up to the failure:\n{joined}"
    
    # Prepare the prompt for AI
    prompt = f"""
An exception occurred in a Python program:

ENVIRONMENT:
Python Version: {python_version}
Platform: {platform}

ERROR DETAILS:
Error Type: {error_type}
Error Message: {error_message}
Function Name: {function_name}
Module: {function_module}

Source Code:
{function_source}

Function Arguments:
{function_arguments}

Exception Attributes:
{exception_attrs}

Traceback:
{traceback}

Detailed Traceback Frames:
{traceback_frames}

Additional Error Details:
{error_details}
{recent_logs}

Based on all the provided context, generate a helpful hint or suggestion for resolving the issue. Consider:
1. The exact error type and message
2. The function's source code
3. The values of arguments passed to the function
4. Any additional error-specific details
5. The full execution context from the traceback

Provide the hint in a concise and clear manner, avoiding any code snippets or markdown formatting.
If the error stems from input data whose structure changed, distinguish renamed fields (same business concept under a new name) from genuinely missing required fields. Never suggest substituting an unrelated field (such as an identifier, order number or date) for a missing required field; in that case recommend raising a clear error instead.
"""
    
    # Get the AI-generated hint with analyzer role
    hint = get_ai_response(prompt, config, system_role="analyzer")
    
    return hint