import logging
import os
import datetime
from typing import Optional
from . import usage_ledger
from .console import emit

def save_ai_fix(context: dict) -> Optional[str]:
    """
    Save AI-generated code fixes to a separate file.
    
    Args:
        context: Dictionary containing the fixed code and context
        
    Returns:
        Optional[str]: Path to the saved fix file, or None if saving failed
    """
    try:
        # Create AI fixes directory if it doesn't exist
        fixes_dir_path = os.path.join(os.path.dirname(context['error']['file']), '_healing_agent_fixes')
        os.makedirs(fixes_dir_path, exist_ok=True)

        # Create a timestamp-based filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        func_name = context.get('function_info', {}).get('name', 'unknown')
        file_path = os.path.join(fixes_dir_path, f"{timestamp}_{func_name}_fix.py")
            
        # Write the fix to file with additional context as comments
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# AI Fix generated on: {datetime.datetime.now()}\n")
                f.write(f"# Original file: {context['error']['file']}\n")
                f.write(f"# Function: {func_name}\n")
                # capture_context writes these as 'type' and 'message'
                # (see exception_handler.capture_context)
                f.write(f"# Error type: {context['error'].get('type', 'Unknown')}\n")
                f.write(f"# Error message: {context['error'].get('message', 'Unknown')}\n")
                f.write(f"# AI Hint: {context.get('ai_hint', 'No hint provided')}\n")
                # Counts only - never prompts. This file sits next to the
                # redacted context and must be as safe to share as that is.
                f.write(f"# Model usage so far this session: {usage_ledger.describe()}\n\n")
                f.write("# Fixed code:\n")
                f.write(context['fixed_code'])

            return file_path

        except Exception as write_error:
            emit(f"♣ Failed to write AI fix to {file_path}: {str(write_error)}", level=logging.ERROR)
            return None

    except Exception as save_error:
        emit(f"♣ Failed to save AI fix: {str(save_error)}", level=logging.ERROR)
        return None 