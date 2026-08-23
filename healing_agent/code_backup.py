import os
import shutil
from datetime import datetime
from typing import Optional
from .console import emit

def create_backup(context: dict) -> Optional[str]:
    """
    Creates a backup of the source file before applying fixes.
    
    Args:
        file_path: Path to the file that needs to be backed up
        config: Configuration dictionary containing backup settings
        
    Returns:
        Optional[str]: Path to the backup file, or None if backup failed
    """

    try:
        backup_folder = os.path.join(os.path.dirname(context['error']['file']), '_healing_agent_backups')
        os.makedirs(backup_folder, exist_ok=True)
        
        # Microsecond precision: repair attempts within the same healing
        # session can land in the same second, and a colliding filename would
        # overwrite the backup holding the pre-healing source.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_name = os.path.basename(context['error']['file'])
        file_name = file_name.replace('.py', '')
        backup_name = f"{file_name}.{timestamp}.py"
        backup_path = os.path.join(backup_folder, backup_name)
        
        # Create the backup
        shutil.copy2(context['error']['file'], backup_path)

        return backup_path
        
    except Exception as e:
        emit(f"⚠ Warning: Failed to create backup: {str(e)}")
        return None


def restore_backup(backup_path: str, target_path: str) -> bool:
    """
    Restore a source file from its backup.

    Used when a healing session ends in definitive failure after the live file
    was already mutated, so no half-healed source is left behind. The generated
    candidate itself stays available under `_healing_agent_fixes/`.

    Args:
        backup_path: Backup created before the first mutation of this session
        target_path: The source file to restore

    Returns:
        bool: True if the file was restored, False if nothing was needed or
              the restore failed
    """
    try:
        if not backup_path or not os.path.exists(backup_path):
            return False

        with open(backup_path, 'rb') as backup_file:
            backup_bytes = backup_file.read()
        try:
            with open(target_path, 'rb') as target_file:
                if target_file.read() == backup_bytes:
                    return False  # File was never mutated; nothing to restore
        except FileNotFoundError:
            pass  # Target vanished; restoring it is still correct

        with open(target_path, 'wb') as target_file:
            target_file.write(backup_bytes)
        return True

    except Exception as e:
        emit(f"⚠ Warning: Failed to restore {target_path} from backup: {str(e)}")
        return False