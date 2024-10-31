from typing import Dict
import time
import httpx
import requests
import openai
from functools import wraps

def handle_connection_errors(provider_name: str):
    """Simple decorator to handle connection errors with basic logging"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (
                httpx.ConnectError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                ConnectionError,
                TimeoutError
            ) as e:
                print(f"♣ Connection error in {provider_name}: {str(e)}")
                # Wait briefly before retrying
                time.sleep(2)
                try:
                    return func(*args, **kwargs)
                except Exception as retry_error:
                    print(f"♣ Retry failed for {provider_name}: {str(retry_error)}")
                    raise
            except openai.APIConnectionError as e:
                if 'OpenAI' in provider_name or 'Azure' in provider_name:
                    print(f"♣ Connection error in {provider_name}: {str(e)}")
                    # Wait briefly before retrying
                    time.sleep(2)
                    try:
                        return func(*args, **kwargs)
                    except Exception as retry_error:
                        print(f"♣ Retry failed for {provider_name}: {str(retry_error)}")
                        raise
                else:
                    raise
            except Exception as e:
                print(f"♣ Unexpected error in {provider_name}: {str(e)}")
                raise
        return wrapper
    return decorator

@handle_connection_errors("Azure")
def _get_azure_response(prompt: str, config: Dict, system_prompt: str) -> str:
    """Handle Azure OpenAI API requests"""
    import openai
    client = openai.AzureOpenAI(
        api_key=config['api_key'],
        api_version=config['api_version'],
        azure_endpoint=config['endpoint']
    )
    
    try:
        response = client.chat.completions.create(
            model=config['deployment_name'],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            timeout=config.get('timeout', 30)
        )
        return response.choices[0].message.content.strip()
    except openai.APIError as e:
        print(f"♣ Azure API error: {str(e)}")
        raise

@handle_connection_errors("OpenAI")
def _get_openai_response(prompt: str, config: Dict, system_prompt: str) -> str:
    """Handle OpenAI direct API requests"""
    import openai
    client = openai.OpenAI(
        api_key=config['api_key'],
        organization=config.get('organization_id')
    )
    
    try:
        response = client.chat.completions.create(
            model=config['model'],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            timeout=config.get('timeout', 30)
        )
        return response.choices[0].message.content.strip()
    except openai.APIError as e:
        print(f"♣ OpenAI API error: {str(e)}")
        raise

@handle_connection_errors("Anthropic")
def _get_anthropic_response(prompt: str, config: Dict) -> str:
    """Handle Anthropic API requests"""
    import anthropic
    client = anthropic.Anthropic(api_key=config['api_key'])
    
    try:
        response = client.messages.create(
            model=config['model'],
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": prompt
            }],
            timeout=config.get('timeout', 30)
        )
        return response.content[0].text
    except Exception as e:
        print(f"♣ Anthropic API error: {str(e)}")
        raise

@handle_connection_errors("Ollama")
def _get_ollama_response(prompt: str, config: Dict) -> str:
    """Handle Ollama API requests"""
    try:
        response = requests.post(
            f"{config['host']}/api/generate",
            json={
                "model": config['model'],
                "prompt": prompt,
                "stream": False
            },
            timeout=config.get('timeout', 120)
        )
        response.raise_for_status()
        return response.json()['response']
    except requests.exceptions.RequestException as e:
        print(f"♣ Ollama API error: {str(e)}")
        raise

@handle_connection_errors("LiteLLM")
def _get_litellm_response(prompt: str, config: Dict, system_prompt: str) -> str:
    """Handle LiteLLM API requests"""
    import litellm
    if config.get('api_base'):
        litellm.api_base = config['api_base']
    
    try:
        response = litellm.completion(
            model=config['model'],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            api_key=config['api_key'],
            timeout=config.get('timeout', 30)
        )
        if not response or not response.choices:
            raise ValueError("Invalid response from LiteLLM API - no choices returned")
            
        if not response.choices[0].message or not response.choices[0].message.content:
            raise ValueError("Invalid response format - missing message content")
            
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"♣ LiteLLM API error: {str(e)}")
        raise

def get_ai_response(prompt: str, config: Dict, system_role: str = "code_fixer") -> str:
    """
    Get response from configured AI provider.
    
    Args:
        prompt (str): The prompt to send to the AI
        config (Dict): Configuration dictionary
        system_role (str): Role for system prompt - "code_fixer", "analyzer", or "report"
    
    Returns:
        str: The AI generated response
    """
    system_prompts = {
        "code_fixer": "You are a Python code fixing assistant. Provide only the corrected code without explanations.",
        "analyzer": "You are a Python error analysis assistant. Provide clear and concise explanation of the error and suggestions to fix it.",
        "report": "You are a Python error reporting assistant. Provide a detailed report of the error, its cause, and the applied fix."
    }
    
    system_prompt = system_prompts.get(system_role, system_prompts["code_fixer"])
    
    try:
        provider = config.get('AI_PROVIDER', 'azure').lower()
        
        if provider == 'azure':
            return _get_azure_response(prompt, config['AZURE'], system_prompt)
        elif provider == 'openai':
            return _get_openai_response(prompt, config['OPENAI'], system_prompt)
        elif provider == 'anthropic':
            return _get_anthropic_response(prompt, config['ANTHROPIC'])
        elif provider == 'ollama':
            return _get_ollama_response(prompt, config['OLLAMA'])
        elif provider == 'litellm':
            return _get_litellm_response(prompt, config['LITELLM'], system_prompt)
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")
            
    except Exception as e:
        print(f"♣ Error getting AI response: {str(e)}")
        raise