# Experimental and not used.

import logging
import json
from typing import Any, Dict
from ..ai_code_fixer import get_ai_response
from ..console import emit

def fix_json_ai(context: Dict[str, Any], config: Dict[str, Any]) -> Any:
    """
    Attempt to fix JSON data using AI.
    """
    try:
        json_data = context['error']['json_details']['response_text']
        
        # Extract the first 1000 characters of the JSON data
        json_snippet = json_data[:1000]
        
        # Prepare the prompt for AI
        prompt = f"""
Fix the following JSON data:

{json_snippet}

Return only the fixed JSON data without any explanations or markdown formatting.
"""
        
        # Get the fix from AI
        fixed_json_str = get_ai_response(prompt, config)
        
        # Parse the fixed JSON string
        fixed_data = json.loads(fixed_json_str)
        
        return fixed_data
    except Exception as e:
        emit(f"♣ JSON fixing with AI failed: {str(e)}", level=logging.ERROR)
        return None

def fix_json_lint(context: Dict[str, Any], config: Dict[str, Any]) -> Any:
    """
    Attempt to fix JSON data using a JSON linter.
    """
    try:
        # Unimplemented stub: reading the payload is all it does today. A real
        # implementation would run a JSON linter over it and return the repaired
        # text; until then the caller falls through to the AI-based fixer.
        _json_data = context['error']['json_details']['response_text']
    except Exception as e:
        emit(f"♣ JSON linting failed: {str(e)}", level=logging.ERROR)
        return None

def fix_json_fallback(context: Dict[str, Any], config: Dict[str, Any]) -> Any:
    """
    Attempt to fix JSON data using fallback parsing options.
    """
    try:
        json_data = context['error']['json_details']['response_text']
        # Use fallback parsing options, e.g., allow trailing commas
        fixed_data = json.loads(json_data, strict=False)
        return fixed_data
    except json.JSONDecodeError as e:
        emit(f"♣ Fallback JSON parsing failed: {str(e)}", level=logging.ERROR)
        return None

def fix_json(context: Dict[str, Any], config: Dict[str, Any]) -> Any:
    """
    Attempt to fix JSON data using the selected strategy.
    """
    strategy = config.get('JSON_FIX_STRATEGY', 'ai')

    if strategy == 'ai':
        return fix_json_ai(context, config)
    elif strategy == 'lint':
        return fix_json_lint(context, config)
    elif strategy == 'fallback':
        return fix_json_fallback(context, config)
    else:
        emit(f"♣ Unknown JSON fix strategy: {strategy}", level=logging.ERROR)
        return None

