import os
import datetime
from typing import Optional

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
                f.write(f"# Error type: {context['error'].get('error_type', 'Unknown')}\n")
                f.write(f"# Error message: {context['error'].get('error_message', 'Unknown')}\n")
                f.write(f"# AI Hint: {context.get('ai_hint', 'No hint provided')}\n\n")
                f.write("# Fixed code:\n")
                f.write(context['fixed_code'])

            return file_path

        except Exception as write_error:
            print(f"♣ Failed to write AI fix to {file_path}: {str(write_error)}")
            return None

    except Exception as save_error:
        print(f"♣ Failed to save AI fix: {str(save_error)}")
        return None 