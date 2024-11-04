import os
import json
import datetime
import traceback
from typing import Optional

def save_context(context: dict) -> Optional[str]:
    """
    Save exception details to a JSON file.
    
    Args:
        context: Dictionary containing exception context and details
        config: Configuration dictionary with save settings
    """
    try:
        # Create exceptions directory if it doesn't exist
        exceptions_dir_path = os.path.join(os.path.dirname(context['error']['file']), '_healing_agent_exceptions')
        os.makedirs(exceptions_dir_path, exist_ok=True)

        # Create a timestamp-based filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        func_name = context.get('function_info', {}).get('name', 'unknown')
        file_path = os.path.join(exceptions_dir_path, f"{timestamp}_{func_name}.json")
            
        # Write exception details to file
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(context, f, indent=2, ensure_ascii=False)

        except Exception as write_error:
            print(f"♣ Failed to write exception details to {file_path}: {str(write_error)}")
            print(f"♣ Write error traceback: {traceback.format_exc()}")
    except Exception as save_error:
        print(f"♣ Failed to save exception details: {str(save_error)}")
        print(f"♣ Save error traceback: {traceback.format_exc()}")

    return file_path