import logging
import os
import json
import datetime
import traceback
from typing import Optional
from .console import emit

#: Upper bound for a saved exception artifact. Generous on purpose: this copy
#: exists to be searched later, so it keeps what a prompt cannot afford.
MAX_ARTIFACT_BYTES = 3 * 1024 * 1024

def save_context(context: dict, config: Optional[dict] = None) -> Optional[str]:
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
            
        # Write exception details to file. The artifact is deliberately the
        # richest copy of the evidence - it is what a later tool searches - so
        # it is capped by total size rather than by per-value truncation, and
        # only trimmed if that cap is actually reached.
        try:
            from .evidence import select

            saved = select(context, config, 'disk')
            payload = json.dumps(saved, indent=2, ensure_ascii=False, default=str)
            if len(payload.encode('utf-8')) > MAX_ARTIFACT_BYTES:
                from .evidence import trim_value

                trimmed = trim_value(saved, 1000)
                trimmed['artifact_note'] = (
                    f'values trimmed: the full context exceeded '
                    f'{MAX_ARTIFACT_BYTES} bytes'
                )
                payload = json.dumps(trimmed, indent=2, ensure_ascii=False, default=str)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(payload)

        except Exception as write_error:
            emit(f"♣ Failed to write exception details to {file_path}: {str(write_error)}", level=logging.ERROR)
            emit(f"♣ Write error traceback: {traceback.format_exc()}")
            # Nothing usable was written; do not hand back a path to a file
            # that does not exist or is half-written.
            file_path = None
    except Exception as save_error:
        emit(f"♣ Failed to save exception details: {str(save_error)}", level=logging.ERROR)
        emit(f"♣ Save error traceback: {traceback.format_exc()}")

    return file_path