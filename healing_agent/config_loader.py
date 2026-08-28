import logging
from pathlib import Path
import os
import shutil
import types
from .console import MODES, emit, set_output_mode
from ._version import CONFIG_SCHEMA_VERSION, parse_version

TEMPLATE_PATH = Path(__file__).with_name('config_template.py')

# Keys that are NEVER auto-filled from the template, because the template only
# holds placeholders for them. Silently defaulting a credential would turn a
# clear "you have not configured a provider" into a confusing auth failure.
_PROVIDER_KEYS = frozenset(
    {'AI_PROVIDER', 'AZURE', 'OPENAI', 'ANTHROPIC', 'OLLAMA', 'LITELLM'}
)

# The version marker is descriptive, not a setting: filling it in from the
# template would make an outdated config claim to be current.
_SCHEMA_MARKER = 'HEALING_AGENT_CONFIG_VERSION'

# load_config() runs on every healing attempt, so the schema notice is emitted
# once per process. It is advice about a file, not an event worth repeating.
_reported_schemas = set()


def _emit_once(key, *messages):
    """Emit a schema notice the first time this process sees it."""
    if key in _reported_schemas:
        return
    _reported_schemas.add(key)
    for message in messages:
        emit(message)


def _load_module(path, module_name):
    """Import a standalone Python file and return the module object."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"♣ Could not load config from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _settings_of(module):
    """Return the configuration settings a config module defines.

    Imports the module pulls in (``import os`` at the top of the template) are
    module objects, not settings, and must not travel with the config.
    """
    return {
        key: value
        for key, value in vars(module).items()
        if not key.startswith('__') and not isinstance(value, types.ModuleType)
    }


def load_template_defaults():
    """Return the settings the shipped config template defines."""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"♣ Config template not found at: {TEMPLATE_PATH}")
    return _settings_of(_load_module(TEMPLATE_PATH, 'healing_agent_config_template'))


def reconcile_config_schema(config_vars, config_path=None):
    """Reconcile a user config with the schema this library expects.

    An older config file is not an error: every behavior key it predates is
    filled in from the template, so upgrading the library never breaks a
    working installation. The user is told once, with the exact key names, so
    the file can be refreshed deliberately instead of silently drifting.
    """
    found = config_vars.get(_SCHEMA_MARKER)
    if parse_version(found) == parse_version(CONFIG_SCHEMA_VERSION):
        return config_vars

    try:
        defaults = load_template_defaults()
    except Exception as template_error:
        emit(f"♣ Could not read the config template for defaults: {template_error}", level=logging.ERROR)
        return config_vars

    if parse_version(found) > parse_version(CONFIG_SCHEMA_VERSION):
        _emit_once(
            ('newer', found),
            f"♣ Config schema {found} is NEWER than this healing_agent expects "
            f"({CONFIG_SCHEMA_VERSION}). Unknown settings are ignored; upgrade "
            f"healing_agent if a setting appears to have no effect.",
        )
        return config_vars

    filled = {}
    for key, value in defaults.items():
        if key == _SCHEMA_MARKER or key in _PROVIDER_KEYS or key in config_vars:
            continue
        config_vars[key] = value
        filled[key] = value

    described = found if isinstance(found, str) and found else 'unversioned'
    location = f" ({config_path})" if config_path else ''
    if filled:
        _emit_once(
            ('older', described, tuple(sorted(filled))),
            f"♣ Config schema {described} predates {CONFIG_SCHEMA_VERSION}"
            f"{location}; using defaults for: {', '.join(sorted(filled))}",
            "♣ To adopt them permanently, add the keys to your config file or "
            "regenerate it from healing_agent/config_template.py",
        )
    else:
        _emit_once(
            ('complete', described),
            f"♣ Config schema {described} predates {CONFIG_SCHEMA_VERSION}"
            f"{location}, but every setting is present. Update "
            f"{_SCHEMA_MARKER} to \"{CONFIG_SCHEMA_VERSION}\" to silence this.",
        )
    return config_vars


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
    emit(f"♣ Created new config file at, please update the values: {user_config_path}")
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
        emit("♣ No config file found. Creating default configuration...")
        config_path = Path(copy_config(user_config))

    # Load config module
    config = _load_module(config_path, "healing_agent_config")

    # Get the settings the config file defines
    config_vars = _settings_of(config)

    # A config written for an older schema keeps working: fill in what it
    # predates before anything reads or validates the settings.
    config_vars = reconcile_config_schema(config_vars, config_path)

    # Check Azure OpenAI config
    if 'AZURE' in config_vars:
        azure_config = config_vars['AZURE']
        if not azure_config.get('api_key'):
            for env_var in ['AZURE_API_KEY', 'AZURE_OPENAI_API_KEY']:
                if os.getenv(env_var):
                    azure_config['api_key'] = os.getenv(env_var)
                    break

        # Env fallbacks MUST use the same keys the AI broker reads:
        # endpoint, deployment_name, api_version (see ai_broker._get_azure_response)
        if not azure_config.get('endpoint'):
            azure_config['endpoint'] = os.getenv('AZURE_OPENAI_ENDPOINT') or os.getenv('AZURE_API_BASE')
        if not azure_config.get('deployment_name'):
            azure_config['deployment_name'] = os.getenv('AZURE_OPENAI_DEPLOYMENT')
        if not azure_config.get('api_version'):
            azure_config['api_version'] = os.getenv('AZURE_API_VERSION') or os.getenv('AZURE_OPENAI_API_VERSION')

    # Check Anthropic config
    if 'ANTHROPIC' in config_vars:
        anthropic_config = config_vars['ANTHROPIC']
        anthropic_config.setdefault('api_key', os.getenv('ANTHROPIC_API_KEY'))
        anthropic_config.setdefault('base_url', os.getenv('ANTHROPIC_BASE_URL'))
        anthropic_config.setdefault('temperature', os.getenv('ANTHROPIC_TEMPERATURE'))
        anthropic_config.setdefault('max_tokens', os.getenv('ANTHROPIC_MAX_TOKENS'))

    # Apply the output mode before anything else reports: from here on the
    # application's logging configuration decides where our messages go.
    set_output_mode(config_vars.get('LOG_MODE', 'auto'))

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
            emit(f"♣ Config validation failed. Missing settings: {', '.join(missing_settings)}")
            emit("♣ Current config keys:", list(config.keys()))
            raise ValueError(f"Missing required settings: {', '.join(missing_settings)}")

        # Validate types
        if not isinstance(config.get('MAX_ATTEMPTS'), int) or config.get('MAX_ATTEMPTS', 0) <= 0:
            raise ValueError("MAX_ATTEMPTS must be a positive integer")
            
        for bool_setting in ['DEBUG', 'AUTO_FIX', 'BACKUP_ENABLED', 'SAVE_EXCEPTIONS']:
            if not isinstance(config.get(bool_setting), bool):
                raise ValueError(f"{bool_setting} must be a boolean value")

        for optional_bool in ['AUTO_SYSCHANGE', 'SAVE_AI_FIXES', 'SAVE_GIT_PATCHES', 'GIT_STAGE', 'RESTORE_ON_FAILURE']:
            if optional_bool in config and not isinstance(config[optional_bool], bool):
                raise ValueError(f"{optional_bool} must be a boolean value")

        environment_vars = config.get('ENVIRONMENT_VARS')
        if environment_vars is not None:
            if isinstance(environment_vars, (str, bytes)) or not isinstance(
                environment_vars, (list, tuple)
            ):
                raise ValueError(
                    "ENVIRONMENT_VARS must be a list of variable names"
                )
            for name in environment_vars:
                if not isinstance(name, str):
                    raise ValueError(
                        f"ENVIRONMENT_VARS entries must be strings, got {name!r}"
                    )
        github = config.get('GITHUB') or {}
        if github.get('pull_request', 'off') not in {'off', 'draft', 'ready'}:
            raise ValueError("GITHUB['pull_request'] must be one of: off, draft, ready")
        capture_chars = config.get('CAPTURE_VALUE_CHARS')
        if capture_chars is not None and (
            isinstance(capture_chars, bool)
            or not isinstance(capture_chars, int)
            or capture_chars <= 0
        ):
            raise ValueError("CAPTURE_VALUE_CHARS must be a positive integer")

        evidence = config.get('EVIDENCE')
        if evidence is not None:
            from .evidence import DEFAULT_EVIDENCE, SECTIONS

            if not isinstance(evidence, dict):
                raise ValueError("EVIDENCE must be a mapping of sink -> section limits")
            for sink, limits in evidence.items():
                if sink not in DEFAULT_EVIDENCE:
                    raise ValueError(
                        f"EVIDENCE has an unknown sink {sink!r}; "
                        f"expected one of: {', '.join(sorted(DEFAULT_EVIDENCE))}"
                    )
                if not isinstance(limits, dict):
                    raise ValueError(f"EVIDENCE[{sink!r}] must be a mapping")
                for section, limit in limits.items():
                    if section not in SECTIONS:
                        raise ValueError(
                            f"EVIDENCE[{sink!r}] has an unknown section {section!r}; "
                            f"expected one of: {', '.join(sorted(SECTIONS))}"
                        )
                    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
                        raise ValueError(
                            f"EVIDENCE[{sink!r}][{section!r}] must be a non-negative integer"
                        )
        if config.get('GIT_MODE', 'off') not in {'off', 'patch', 'apply'}:
            raise ValueError("GIT_MODE must be one of: off, patch, apply")
        if config.get('GIT_PATCH_DIR') is not None and not isinstance(config.get('GIT_PATCH_DIR'), (str, os.PathLike)):
            raise ValueError("GIT_PATCH_DIR must be a path string or None")
        if config.get('LOG_MODE', 'auto') not in MODES:
            raise ValueError(f"LOG_MODE must be one of: {', '.join(MODES)}")
        if config.get('VERIFY_COMMAND') is not None and not isinstance(config.get('VERIFY_COMMAND'), (str, list, tuple)):
            raise ValueError("VERIFY_COMMAND must be a command string, argument list, or None")
        if (
            isinstance(config.get('VERIFY_TIMEOUT_SECONDS'), bool)
            or not isinstance(config.get('VERIFY_TIMEOUT_SECONDS', 120), (int, float))
            or config.get('VERIFY_TIMEOUT_SECONDS', 120) <= 0
        ):
            raise ValueError("VERIFY_TIMEOUT_SECONDS must be a positive number")
    
        return config
        
    except Exception as e:
        emit(f"♣ Error loading config: {str(e)}", level=logging.ERROR)
        raise
