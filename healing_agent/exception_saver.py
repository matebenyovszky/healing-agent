import os
import json
import datetime
import traceback
from typing import Optional
from .console import emit

def save_context(context: dict) -> Optional[str]:
    """
    Save exception details to a JSON file.
    
    Args:
        context: Dictionary containing exception context and details
        config: Configuration dictionary with save settings
    """
    # Bound before the try: if building the path fails, the function must
    # report the failure by returning None, not raise UnboundLocalError from
    # the return statement and mask the application's own exception.
    file_path = None
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
            emit(f"♣ Failed to write exception details to {file_path}: {str(write_error)}")
            emit(f"♣ Write error traceback: {traceback.format_exc()}")
            # Nothing usable was written; do not hand back a path to a file
            # that does not exist or is half-written.
            file_path = None
    except Exception as save_error:
        emit(f"♣ Failed to save exception details: {str(save_error)}")
        emit(f"♣ Save error traceback: {traceback.format_exc()}")

    return file_path