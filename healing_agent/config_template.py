# Healing Agent Configuration File
# -------------------------------
# This file contains all configuration options for the Healing Agent library.
# You can customize the AI provider, model settings, and other behaviors.

# AI Provider Configuration
# -----------------------
# Supported providers: 'azure', 'openai', 'ollama', 'litellm', 'anthropic'
import os

HEALING_AGENT_CONFIG_VERSION = "0.2.6"  
AI_PROVIDER = "azure"  

# Azure OpenAI Configuration
# ------------------------
AZURE = {
    "api_key": os.getenv("AZURE_OPENAI_API_KEY", "XXX"),
    "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", "https://XXX.openai.azure.com"),
    "deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
    "api_version": "2024-02-01"
}

# OpenAI Direct Configuration  
# -------------------------
OPENAI = {
    "api_key": os.getenv("OPENAI_API_KEY", "your-openai-key-here"),
    "model": os.getenv("OPENAI_MODEL", "gpt-4"),  # or gpt-3.5-turbo
    "organization_id": os.getenv("OPENAI_ORG_ID", None)  # Optional
}

# Anthropic Configuration
# ---------------------
ANTHROPIC = {
    "api_key": os.getenv("ANTHROPIC_API_KEY", "your-anthropic-key-here"),
    "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),  # e.g. claude-sonnet-5, claude-haiku-4-5
    "max_tokens": int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024")),
    "temperature": float(os.getenv("ANTHROPIC_TEMPERATURE", "1.0"))
}

# Ollama Configuration
# ------------------
OLLAMA = {
    "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),  # Default Ollama host
    "model": os.getenv("OLLAMA_MODEL", "llama3"),  # or codellama, mistral etc.
    "timeout": int(os.getenv("OLLAMA_TIMEOUT", "120"))  # Request timeout in seconds
}

# LiteLLM Configuration
# -------------------
LITELLM = {
    "api_key": os.getenv("LITELLM_API_KEY", "your-litellm-key"),  # If using hosted LiteLLM
    "model": os.getenv("LITELLM_MODEL", "gpt-4"),  # Model identifier
    "api_base": os.getenv("LITELLM_API_BASE", None)  # Optional custom API base URL
}

# Healing Agent Behavior Configuration
# ---------------------------------
MAX_ATTEMPTS = 3  # Maximum number of fix attempts
DEBUG = True  # Enable detailed logging
AUTO_FIX = True  # Automatically apply fixes without confirmation
AUTO_SYSCHANGE = True  # Automatically apply system changes without confirmation

# Healing Agent System Prompts
# ---------------------------
SYSTEM_PROMPTS = {
    "code_fixer": "You are a Python code fixing assistant. Provide only the corrected code without explanations.",
    "analyzer": "You are a Python error analysis assistant. Provide clear and concise explanation of the error and suggestions to fix it.",
    "report": "You are a Python error reporting assistant. Provide a detailed report of the error, its cause, and the applied fix."
}

# Backup and Storage Configuration
# -----------------------------
BACKUP_ENABLED = True  # Enable code backups before fixes
SAVE_EXCEPTIONS = True  # Save exception contexts for analysis
SAVE_AI_FIXES = True  # New parameter to control saving AI code suggestions

# Secret Redaction Configuration
# -----------------------------
# Captured context (variables, arguments, headers, exception attributes) is
# written to disk and sent to the AI provider. Name-based redaction replaces
# the value of any field whose NAME looks sensitive before that happens.
REDACT_SECRETS = True  # Master switch for secret redaction (strongly recommended: True)
REDACT_PLACEHOLDER = "<redacted>"  # Replacement text for redacted values
# Extra case-insensitive regex/substring patterns to treat as sensitive field
# names, on top of the built-in defaults (password, token, api_key, auth, ...).
REDACT_EXTRA_PATTERNS = []  # e.g. ["adószám", "taj", "customer[-_ ]?id"]