# Healing Agent Configuration File
# -------------------------------
# This file contains all configuration options for the Healing Agent library.
# You can customize the AI provider, model settings, and other behaviors.

# AI Provider Configuration
# -----------------------
# Supported providers: 'azure', 'openai', 'ollama', 'litellm', 'anthropic'
AI_PROVIDER = "azure"  

# Azure OpenAI Configuration
# ------------------------
AZURE = {
    "api_key": "f484cfe7823a4de9860e9badb016e28e",
    "endpoint": "https://sandbox-ai-swedencentral.openai.azure.com",
    "deployment_name": "gpt-4o-mini",
    "api_version": "2024-02-01"
}

# OpenAI Direct Configuration  
# -------------------------
OPENAI = {
    "api_key": "your-openai-key-here",
    "model": "gpt-4",  # or gpt-3.5-turbo
    "organization_id": None  # Optional
}

# Anthropic Configuration
# ---------------------
ANTHROPIC = {
    "api_key": "your-anthropic-key-here",
    "model": "claude-2"  # or claude-instant-1
}

# Ollama Configuration
# ------------------
OLLAMA = {
    "host": "http://localhost:11434",  # Default Ollama host
    "model": "llama2",  # or codellama, mistral etc.
    "timeout": 120  # Request timeout in seconds
}

# LiteLLM Configuration
# -------------------
LITELLM = {
    "api_key": "your-litellm-key",  # If using hosted LiteLLM
    "model": "gpt-4",  # Model identifier
    "api_base": None  # Optional custom API base URL
}

# Healing Agent Behavior Configuration
# ---------------------------------
MAX_ATTEMPTS = 3  # Maximum number of fix attempts
DEBUG = True  # Enable detailed logging
AUTO_FIX = True  # Automatically apply fixes without confirmation

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
