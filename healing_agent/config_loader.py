from pathlib import Path
import os
import shutil

def copy_config(user_config_path):
    """
    Sets up the healing agent configuration file by copying example config to specified path.
    
    Args:
        user_config_path (Path): Path where config file should be created
        
    Returns:
        str: Path to the created config file
    """
    os.makedirs(os.path.dirname(user_config_path), exist_ok=True)
        
    # Copy example config using platform-agnostic paths
    example_config = os.path.join(os.path.dirname(__file__), 'config_template.py')
    if not os.path.exists(example_config):
        raise FileNotFoundError(f"♣ Config template not found at: {example_config}")
        
    shutil.copy(example_config, user_config_path)
    print(f"♣ Created new config file at, please update the values: {user_config_path}")
    return user_config_path

def load_config(local_config_path=None):
    """
    Load configuration from healing_agent_config.py
    
    Args:
        local_config_path (str|Path, optional): Path to local config file. If not provided,
            will attempt to detect config location automatically.
    """

    user_config = Path.home() / '.healing_agent' / 'healing_agent_config.py'
    
    if local_config_path and Path(local_config_path).exists():
        config_path = Path(local_config_path)
    elif user_config.exists():
        config_path = Path(user_config)
    else:
        # Create default config
        print("♣ No config file found. Creating default configuration...")
        config_path = Path(copy_config(user_config))

    # Load config module
    import importlib.util
    spec = importlib.util.spec_from_file_location("healing_agent_config", config_path)
    if spec is None:
        raise ImportError(f"♣ Could not load config from {config_path}")
        
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    
    # Get non-private variables from config
    config_vars = {k: v for k, v in vars(config).items() 
                  if not k.startswith('__')}
    
    # Check Azure OpenAI config
    if 'AZURE' in config_vars:
        azure_config = config_vars['AZURE']
        if not azure_config.get('api_key'):
            for env_var in ['AZURE_API_KEY', 'AZURE_OPENAI_API_KEY']:
                if os.getenv(env_var):
                    azure_config['api_key'] = os.getenv(env_var)
                    break
                    
        azure_config.setdefault('instance', os.getenv('AZURE_OPENAI_INSTANCE'))
        azure_config.setdefault('api_version', os.getenv('AZURE_API_VERSION'))
        azure_config.setdefault('api_base', os.getenv('AZURE_API_BASE'))

    # Check Anthropic config
    if 'ANTHROPIC' in config_vars:
        anthropic_config = config_vars['ANTHROPIC']
        anthropic_config.setdefault('api_key', os.getenv('ANTHROPIC_API_KEY'))
        anthropic_config.setdefault('base_url', os.getenv('ANTHROPIC_BASE_URL'))
        anthropic_config.setdefault('temperature', os.getenv('ANTHROPIC_TEMPERATURE'))
        anthropic_config.setdefault('max_tokens', os.getenv('ANTHROPIC_MAX_TOKENS'))

    # Validate config
    validate_config(config_vars)
            
    return config_vars, config_path

def validate_config(config):
    """Validate configuration settings."""
    try:
        # Validate AI provider
        if 'AI_PROVIDER' not in config:
            raise ValueError("AI_PROVIDER must be defined in config")
            
        valid_providers = ['azure', 'openai', 'ollama', 'litellm', 'anthropic']
        if config['AI_PROVIDER'] not in valid_providers:
            raise ValueError(f"♣ Invalid AI provider: {config['AI_PROVIDER']}. Must be one of: {', '.join(valid_providers)}")
            
        # Validate provider-specific settings
        if config['AI_PROVIDER'] == 'azure':
            if not (config.get('AZURE', {}).get('api_key') and config.get('AZURE', {}).get('endpoint')):
                raise ValueError("Azure API key and endpoint must be configured")
                
        elif config['AI_PROVIDER'] == 'openai':
            if not config.get('OPENAI', {}).get('api_key'):
                raise ValueError("OpenAI API key must be configured")
                
        elif config['AI_PROVIDER'] == 'anthropic':
            if not config.get('ANTHROPIC', {}).get('api_key'):
                raise ValueError("Anthropic API key must be configured")

        # Validate behavior configuration
        required_settings = ['MAX_ATTEMPTS', 'DEBUG', 'AUTO_FIX', 'BACKUP_ENABLED', 'SAVE_EXCEPTIONS', 'SYSTEM_PROMPTS']
        missing_settings = []
        for setting in required_settings:
            if setting not in config:
                # For SYSTEM_PROMPTS, check if it exists and has required keys
                if setting == 'SYSTEM_PROMPTS':
                    if not config.get('SYSTEM_PROMPTS') or not all(key in config['SYSTEM_PROMPTS'] for key in ['code_fixer', 'analyzer', 'report']):
                        missing_settings.append(setting)
                else:
                    missing_settings.append(setting)
                    
        if missing_settings:
            print(f"♣ Config validation failed. Missing settings: {', '.join(missing_settings)}")
            print("♣ Current config keys:", list(config.keys()))
            raise ValueError(f"Missing required settings: {', '.join(missing_settings)}")

        # Validate types
        if not isinstance(config.get('MAX_ATTEMPTS'), int) or config.get('MAX_ATTEMPTS', 0) <= 0:
            raise ValueError("MAX_ATTEMPTS must be a positive integer")
            
        for bool_setting in ['DEBUG', 'AUTO_FIX', 'BACKUP_ENABLED', 'SAVE_EXCEPTIONS']:
            if not isinstance(config.get(bool_setting), bool):
                raise ValueError(f"{bool_setting} must be a boolean value")
    
        return config
        
    except Exception as e:
        print(f"♣ Error loading config: {str(e)}")
        raise