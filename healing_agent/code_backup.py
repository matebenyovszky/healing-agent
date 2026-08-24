import logging
import os
import shutil
from datetime import datetime
from typing import Optional
from .console import emit

def _claim_backup_path(backup_folder: str, stem: str, timestamp: str) -> str:
    """Claim a backup filename that is guaranteed not to exist yet.

    The clock is NOT a source of uniqueness. `datetime.now()` has millisecond
    or worse granularity on Windows, so two backups taken in quick succession —
    exactly what a second repair attempt does — can carry the identical
    microsecond field. The second copy would then overwrite the first, and the
    first is the one holding the PRE-HEALING source: `_register_backup()` keeps
    only the earliest backup per file, so restore-on-failure would faithfully
    restore the mutated code it exists to undo.

    `O_CREAT | O_EXCL` claims the name atomically, so a numeric suffix is added
    only when the name is genuinely taken, including by a concurrent process.
    """
    for suffix in range(1000):
        name = f"{stem}.{timestamp}.py" if suffix == 0 else (
            f"{stem}.{timestamp}_{suffix}.py"
        )
        path = os.path.join(backup_folder, name)
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path
        except FileExistsError:
            continue
    raise FileExistsError(
        f"Could not claim a unique backup name for {stem} in {backup_folder}"
    )


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
        
        # The timestamp makes the name readable and roughly ordered; the
        # collision handling in _claim_backup_path is what makes it unique.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        # splitext, not replace('.py', ''): replace strips EVERY occurrence,
        # so "loader.python.py" would become "loaderthon".
        stem = os.path.splitext(os.path.basename(context['error']['file']))[0]
        backup_path = _claim_backup_path(backup_folder, stem, timestamp)

        # Create the backup, overwriting the empty file that claimed the name
        shutil.copy2(context['error']['file'], backup_path)

        return backup_path
        
    except Exception as e:
        emit(f"⚠ Warning: Failed to create backup: {str(e)}", level=logging.WARNING)
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
        emit(f"⚠ Warning: Failed to restore {target_path} from backup: {str(e)}", level=logging.WARNING)
        return False