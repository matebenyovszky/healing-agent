from pathlib import Path
from .configurator import setup_config

def load_config():
    """Load configuration from healing_agent_config.py"""
    # First check local directory
    local_config = Path('healing_agent_config.py')
    user_config = Path.home() / '.healing_agent' / 'healing_agent_config.py'
    
    if local_config.exists():
        config_path = local_config
    elif user_config.exists():
        config_path = user_config
    else:
        # Run configurator to create default config
        print("♣ No config file found. Creating default configuration...")
        config_path = Path(setup_config())
        print("♣ Please update the configuration values in the newly created config file")
        return {
            'save_exception': False,
            'exception_folder': str(Path.home() / '.healing_agent' / 'exceptions')
        }
        
    import importlib.util
    spec = importlib.util.spec_from_file_location("healing_agent_config", config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    
    # Get all variables from config module
    config_vars = {k: v for k, v in vars(config).items() 
                  if not k.startswith('__')}
    
    # Set defaults for required config values if not present
    if 'SAVE_EXCEPTION' not in config_vars:
        config_vars['SAVE_EXCEPTION'] = False
    if 'EXCEPTION_FOLDER' not in config_vars:
        config_vars['EXCEPTION_FOLDER'] = str(Path.home() / '.healing_agent' / 'exceptions')
        
    return config_vars