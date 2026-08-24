import logging
from typing import Any, Dict, Optional
import time
import httpx
import requests
from functools import wraps
from . import usage_ledger
from .console import emit

_NETWORK_ERRORS = (
    httpx.ConnectError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    ConnectionError,
    TimeoutError,
)

def _openai_connection_error():
    """openai's connection-error class, or None when openai is not installed.

    The openai package is only needed by the azure and openai providers, so it
    is imported where it is used rather than at module import: an Ollama-only
    or LiteLLM-only install should not fail because a package it never calls is
    missing.
    """
    try:
        import openai
    except ImportError:
        return None
    return openai.APIConnectionError

def _is_transient(error: Exception, provider_name: str) -> bool:
    """True for failures a single immediate retry can plausibly fix."""
    if isinstance(error, _NETWORK_ERRORS):
        return True
    openai_connection_error = _openai_connection_error()
    if openai_connection_error is not None and isinstance(error, openai_connection_error):
        return 'OpenAI' in provider_name or 'Azure' in provider_name
    return False

def handle_connection_errors(provider_name: str):
    """Simple decorator to handle connection errors with basic logging"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if not _is_transient(e, provider_name):
                    emit(f"♣ Unexpected error in {provider_name}: {str(e)}")
                    raise
                emit(f"♣ Connection error in {provider_name}: {str(e)}")
                # Wait briefly before retrying
                time.sleep(2)
                try:
                    return func(*args, **kwargs)
                except Exception as retry_error:
                    emit(f"♣ Retry failed for {provider_name}: {str(retry_error)}")
                    raise
        return wrapper
    return decorator

def _as_int(value: Any) -> Optional[int]:
    """Token counts only when the provider really reported one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def _record_usage(
    provider: str,
    model: Optional[str],
    started: float,
    prompt_tokens: Any = None,
    completion_tokens: Any = None,
) -> None:
    """Add this call to the healing session's ledger.

    Each provider maps its OWN response shape here rather than sharing a
    normalizer, because the shapes genuinely differ (`prompt_tokens` /
    `input_tokens` / `prompt_eval_count`) and a shared guesser would quietly
    return None for whichever provider changed last.
    """
    usage_ledger.record(
        provider=provider,
        model=model,
        seconds=round(time.perf_counter() - started, 3),
        prompt_tokens=_as_int(prompt_tokens),
        completion_tokens=_as_int(completion_tokens),
    )

def _params(config: Dict) -> Dict:
    """Return the provider block's sampling parameters, forwarded verbatim.

    A provider block may carry ``"params": {...}`` — temperature, seed, top_p,
    ``num_ctx``, whatever that provider accepts. Healing Agent does not
    validate or translate the contents: the provider owns its own parameter
    names, and a whitelist here would go stale with every API release.

    Absent, empty or malformed means "send nothing", so a config without
    ``params`` produces exactly the requests previous releases sent.
    """
    params = config.get('params') or {}
    if not isinstance(params, dict):
        emit("♣ Ignoring 'params': expected a dict of provider sampling options")
        return {}
    return dict(params)

@handle_connection_errors("Azure")
def _get_azure_response(prompt: str, config: Dict, system_prompt: str) -> str:
    """Handle Azure OpenAI API requests"""
    import openai
    client = openai.AzureOpenAI(
        api_key=config['api_key'],
        api_version=config['api_version'],
        azure_endpoint=config['endpoint']
    )
    
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=config['deployment_name'],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            timeout=config.get('timeout', 30),
            **_params(config)
        )
        usage = getattr(response, 'usage', None)
        _record_usage(
            'azure', config.get('deployment_name'), started,
            getattr(usage, 'prompt_tokens', None),
            getattr(usage, 'completion_tokens', None)
        )
        return response.choices[0].message.content.strip()
    except openai.APIError as e:
        emit(f"♣ Azure API error: {str(e)}")
        raise

@handle_connection_errors("OpenAI")
def _get_openai_response(prompt: str, config: Dict, system_prompt: str) -> str:
    """Handle OpenAI direct API requests"""
    import openai
    client = openai.OpenAI(
        api_key=config['api_key'],
        organization=config.get('organization_id')
    )
    
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=config['model'],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            timeout=config.get('timeout', 30),
            **_params(config)
        )
        usage = getattr(response, 'usage', None)
        _record_usage(
            'openai', config.get('model'), started,
            getattr(usage, 'prompt_tokens', None),
            getattr(usage, 'completion_tokens', None)
        )
        return response.choices[0].message.content.strip()
    except openai.APIError as e:
        emit(f"♣ OpenAI API error: {str(e)}")
        raise

@handle_connection_errors("Anthropic")
def _get_anthropic_response(prompt: str, config: Dict, system_prompt: str) -> str:
    """Handle Anthropic API requests"""
    import anthropic
    client = anthropic.Anthropic(api_key=config['api_key'])

    try:
        request_kwargs = {
            "model": config.get('model', 'claude-sonnet-5'),
            "max_tokens": int(config.get('max_tokens') or 1024),
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": config.get('timeout', 30)
        }
        # Only pass temperature if explicitly configured (else use SDK default)
        if config.get('temperature') is not None:
            request_kwargs["temperature"] = float(config['temperature'])

        # An explicit params entry wins over the block-level shorthands above,
        # so a benchmark sweep can override temperature per run.
        request_kwargs.update(_params(config))

        started = time.perf_counter()
        response = client.messages.create(**request_kwargs)
        usage = getattr(response, 'usage', None)
        _record_usage(
            'anthropic', request_kwargs.get('model'), started,
            getattr(usage, 'input_tokens', None),
            getattr(usage, 'output_tokens', None)
        )
        return response.content[0].text
    except Exception as e:
        emit(f"♣ Anthropic API error: {str(e)}")
        raise

@handle_connection_errors("Ollama")
def _get_ollama_response(prompt: str, config: Dict) -> str:
    """Handle Ollama API requests"""
    payload = {
        "model": config['model'],
        "prompt": prompt,
        "stream": False
    }
    # Ollama takes sampling parameters (temperature, seed, top_p, num_ctx,
    # num_predict) inside "options" rather than at the top level.
    options = _params(config)
    if options:
        payload["options"] = options

    started = time.perf_counter()
    try:
        response = requests.post(
            f"{config['host']}/api/generate",
            json=payload,
            timeout=config.get('timeout', 120)
        )
        response.raise_for_status()
        body = response.json()
        # Ollama reports counts in the generate response itself.
        _record_usage(
            'ollama', config.get('model'), started,
            body.get('prompt_eval_count'),
            body.get('eval_count')
        )
        return body['response']
    except requests.exceptions.RequestException as e:
        emit(f"♣ Ollama API error: {str(e)}")
        raise

@handle_connection_errors("LiteLLM")
def _get_litellm_response(prompt: str, config: Dict, system_prompt: str) -> str:
    """Handle LiteLLM API requests"""
    import litellm

    request_kwargs = {
        "model": config['model'],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "api_key": config['api_key'],
        "timeout": config.get('timeout', 30),
    }
    # Per call, never `litellm.api_base = ...`: that is module-global state,
    # so it outlived this call and applied to every later one — including
    # calls made by other code sharing the process.
    if config.get('api_base'):
        request_kwargs["api_base"] = config['api_base']
    request_kwargs.update(_params(config))

    started = time.perf_counter()
    try:
        response = litellm.completion(**request_kwargs)
        usage = getattr(response, 'usage', None)
        _record_usage(
            'litellm', config.get('model'), started,
            getattr(usage, 'prompt_tokens', None),
            getattr(usage, 'completion_tokens', None)
        )
        if not response or not response.choices:
            raise ValueError("Invalid response from LiteLLM API - no choices returned")
            
        if not response.choices[0].message or not response.choices[0].message.content:
            raise ValueError("Invalid response format - missing message content")
            
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        emit(f"♣ LiteLLM API error: {str(e)}")
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
    # system_prompts = config.get('SYSTEM_PROMPTS', {
    #     "code_fixer": "You are a Python code fixing assistant. Provide only the corrected code without explanations.",
    #     "analyzer": "You are a Python error analysis assistant. Provide clear and concise explanation of the error and suggestions to fix it.", 
    #     "report": "You are a Python error reporting assistant. Provide a detailed report of the error, its cause, and the applied fix."
    # })
    
    system_prompts = config['SYSTEM_PROMPTS'] if 'SYSTEM_PROMPTS' in config else {
        "code_fixer": "You are a Python code fixing assistant. Provide only the corrected code without explanations.",
        "analyzer": "You are a Python error analysis assistant. Provide clear and concise explanation of the error and suggestions to fix it.", 
        "report": "You are a Python error reporting assistant. Provide a detailed report of the error, its cause, and the applied fix."
    }
    
    system_prompt = system_prompts.get(system_role, system_prompts["code_fixer"])
    
    try:
        provider = config['AI_PROVIDER'].lower() if 'AI_PROVIDER' in config else 'azure'
        if provider == 'azure':
            return _get_azure_response(prompt, config['AZURE'], system_prompt)
        elif provider == 'openai':
            return _get_openai_response(prompt, config['OPENAI'], system_prompt)
        elif provider == 'anthropic':
            return _get_anthropic_response(prompt, config['ANTHROPIC'], system_prompt)
        elif provider == 'ollama':
            return _get_ollama_response(prompt, config['OLLAMA'])
        elif provider == 'litellm':
            return _get_litellm_response(prompt, config['LITELLM'], system_prompt)
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")
            
    except Exception as e:
        emit(f"♣ Error getting AI response: {str(e)}", level=logging.ERROR)
        raise