import os
import shutil

def setup_config():
    """
    Sets up the healing agent configuration file by checking for local config,
    then user directory config, and copying example config if neither exists.
    
    Returns:
        str: Path to the config file being used
    """
    # Check for config file in current directory first
    local_config = 'healing_agent_config.py'
    config_path = os.path.expanduser('~/.healing_agent/healing_agent_config.py')

    if os.path.exists(local_config):
        print(f"✓ Using local config file: {local_config}")
        return local_config
    elif os.path.exists(config_path):
        print(f"✓ Using config file from: {config_path}")
        return config_path
    else:
        # Create the .healing_agent directory if it doesn't exist
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # Get the absolute path to the example config file
        example_config = os.path.join(os.path.dirname(__file__), 'healing_agent_config.py')
        
        # Copy the example config using platform-agnostic paths
        shutil.copy(example_config, config_path)
        print(f"♣ Created new config file at, please update the values: {config_path}")
        return config_path
if __name__ == "__main__":
    setup_config()