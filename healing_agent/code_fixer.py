import re
from typing import Dict, Any

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

def get_ai_response(prompt: str, config: Dict) -> str:
    """
    Get response from configured AI provider.
    
    Args:
        prompt (str): The prompt to send to the AI
    
    Returns:
        str: The AI generated response
    """
    try:
        provider = config.get('AI_PROVIDER', 'azure').lower()
        
        if provider == 'azure':
            return _get_azure_response(prompt, config['AZURE'])
        elif provider == 'openai':
            return _get_openai_response(prompt, config['OPENAI'])
        elif provider == 'anthropic':

            return _get_anthropic_response(prompt, config['ANTHROPIC'])
        elif provider == 'ollama':
            return _get_ollama_response(prompt, config['OLLAMA'])
        elif provider == 'litellm':
            return _get_litellm_response(prompt, config['LITELLM'])
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")
            
    except Exception as e:
        print(f"♣ Error getting AI response: {str(e)}")
        raise

def _get_azure_response(prompt: str, config: Dict) -> str:
    """Handle Azure OpenAI API requests"""
    import openai
    client = openai.AzureOpenAI(
        api_key=config['api_key'],
        api_version=config['api_version'],
        azure_endpoint=config['endpoint']
    )
    
    response = client.chat.completions.create(
        model=config['deployment_name'],
        messages=[
            {"role": "system", "content": "You are a Python code fixing assistant. Provide only the corrected code without explanations."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()

def _get_openai_response(prompt: str, config: Dict) -> str:
    """Handle OpenAI direct API requests"""
    import openai
    client = openai.OpenAI(
        api_key=config['api_key'],
        organization=config.get('organization_id')
    )
    
    response = client.chat.completions.create(
        model=config['model'],
        messages=[
            {"role": "system", "content": "You are a Python code fixing assistant. Provide only the corrected code without explanations."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()

def _get_anthropic_response(prompt: str, config: Dict) -> str:
    """Handle Anthropic API requests"""
    import anthropic
    client = anthropic.Anthropic(api_key=config['api_key'])
    
    response = client.messages.create(
        model=config['model'],
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    return response.content[0].text

def _get_ollama_response(prompt: str, config: Dict) -> str:
    """Handle Ollama API requests"""
    import requests
    
    response = requests.post(
        f"{config['host']}/api/generate",
        json={
            "model": config['model'],
            "prompt": prompt,
            "stream": False
        },
        timeout=config.get('timeout', 120)
    )
    return response.json()['response']

def _get_litellm_response(prompt: str, config: Dict) -> str:
    """Handle LiteLLM API requests"""
    import litellm
    if config.get('api_base'):
        litellm.api_base = config['api_base']
    
    response = litellm.completion(
        model=config['model'],
        messages=[
            {"role": "system", "content": "You are a Python code fixing assistant. Provide only the corrected code without explanations."},
            {"role": "user", "content": prompt}
        ],
        api_key=config['api_key']
    )
    return response.choices[0].message.content.strip()

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

    return f"""
Fix the following Python code that produced an error:

Original Code:
{context['function_info']['source_code']}

Error Type: {context['error']['type']}
Error Message: {context['error']['message']}

Stack Trace:
{context['error']['traceback']}
{func_info}{arg_info}
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
        
        # Get the fix from AI
        fixed_code = get_ai_response(prompt, config)

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
