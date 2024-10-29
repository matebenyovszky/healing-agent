import os
import shutil
from datetime import datetime
from typing import Optional


def create_backup(file_path: str, config: dict) -> Optional[str]:
    """
    Creates a backup of the source file before applying fixes.
    
    Args:
        file_path: Path to the file that needs to be backed up
        config: Configuration dictionary containing backup settings
        
    Returns:
        Optional[str]: Path to the backup file, or None if backup failed
    """

    backup_folder = config.get('BACKUP_FOLDER', './healing_agent_backups')
    debug = config.get('DEBUG', False)
       
    try:
        # Ensure backup directory exists
        os.makedirs(backup_folder, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = os.path.basename(file_path)
        file_name = file_name.replace('.py', '')
        backup_name = f"{file_name}.{timestamp}.py"
        backup_path = os.path.join(backup_folder, backup_name)
        
        # Create the backup
        shutil.copy2(file_path, backup_path)
        if debug:
            print(f"♣ Created backup at: {backup_path}")
        return backup_path
        
    except Exception as e:
        print(f"⚠ Warning: Failed to create backup: {str(e)}")
        return None