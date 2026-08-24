# Healing Agent Configuration File
# -------------------------------
# This file contains all configuration options for the Healing Agent library.
# You can customize the AI provider, model settings, and other behaviors.

# AI Provider Configuration
# -----------------------
# Supported providers: 'azure', 'openai', 'ollama', 'litellm', 'anthropic'
import os

# Marks the SCHEMA this file follows - which keys exist - not the version of
# the installed library. It changes only when a configuration key is added,
# renamed or removed, and is then set to the release that ships that change.
# healing_agent compares it with its own CONFIG_SCHEMA_VERSION on load and
# fills in any behavior key this file predates, so an older config keeps working.
HEALING_AGENT_CONFIG_VERSION = "0.4.0"
AI_PROVIDER = os.getenv("HEALING_AGENT_PROVIDER", "azure")

# Sampling parameters
# -------------------
# Every provider block below accepts an optional "params" dict. Its contents
# are forwarded to that provider VERBATIM — Healing Agent neither validates nor
# translates them, because the provider owns its own parameter names.
#   azure / openai / litellm : request keyword arguments
#                              e.g. {"temperature": 0.2, "seed": 7}
#   anthropic                : request keyword arguments; overrides the
#                              max_tokens / temperature shorthands below
#   ollama                   : sent inside Ollama's "options" object
#                              e.g. {"temperature": 0.2, "seed": 7, "num_ctx": 8192}
# Leave it empty to send exactly what earlier releases sent (provider defaults).
# Note that a small local model with a short num_ctx may silently truncate the
# captured context, which looks like a repair failure but is a setup failure.

# Azure OpenAI Configuration
# ------------------------
AZURE = {
    "api_key": os.getenv("AZURE_OPENAI_API_KEY", "XXX"),
    "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", "https://XXX.openai.azure.com"),
    "deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
    "api_version": "2024-02-01",
    "params": {}
}

# OpenAI Direct Configuration  
# -------------------------
OPENAI = {
    "api_key": os.getenv("OPENAI_API_KEY", "your-openai-key-here"),
    # Any Chat Completions-compatible model ID can be used. This balanced
    # default should still be evaluated against your own repair benchmark.
    "model": os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
    "organization_id": os.getenv("OPENAI_ORG_ID", None),  # Optional
    "params": {}
}

# Anthropic Configuration
# ---------------------
ANTHROPIC = {
    "api_key": os.getenv("ANTHROPIC_API_KEY", "your-anthropic-key-here"),
    "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),  # e.g. claude-sonnet-5, claude-haiku-4-5
    "max_tokens": int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024")),
    "temperature": float(os.getenv("ANTHROPIC_TEMPERATURE", "1.0")),
    "params": {}
}

# Ollama Configuration
# ------------------
OLLAMA = {
    "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),  # Default Ollama host
    "model": os.getenv("OLLAMA_MODEL", "llama3"),  # or codellama, mistral etc.
    "timeout": int(os.getenv("OLLAMA_TIMEOUT", "120")),  # Request timeout in seconds
    "params": {}  # -> Ollama "options": temperature, seed, top_p, num_ctx, ...
}

# LiteLLM Configuration
# -------------------
LITELLM = {
    "api_key": os.getenv("LITELLM_API_KEY", "your-litellm-key"),  # If using hosted LiteLLM
    "model": os.getenv("LITELLM_MODEL", "openai/gpt-5.6-terra"),
    "api_base": os.getenv("LITELLM_API_BASE", None),  # Optional custom API base URL
    "params": {}
}

# Healing Agent Behavior Configuration
# ---------------------------------
MAX_ATTEMPTS = 3  # Maximum number of fix attempts
DEBUG = True  # Enable detailed logging
AUTO_FIX = True  # Preserve classic behavior: apply and execute generated fixes
AUTO_SYSCHANGE = False  # Safer default: never install packages automatically

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
# When healing ends in definitive failure (MAX_ATTEMPTS exhausted or the
# repaired module still fails) restore the pre-healing source from the backup,
# so no half-healed file is left behind. The generated candidate is still kept
# under _healing_agent_fixes/. Requires BACKUP_ENABLED=True.
RESTORE_ON_FAILURE = True
SAVE_EXCEPTIONS = True  # Save exception contexts for analysis
SAVE_AI_FIXES = True  # New parameter to control saving AI code suggestions
SAVE_GIT_PATCHES = False  # Optionally emit a reviewable `git apply` patch
# Git integration is language-neutral and opt-in:
#   off   - no Git interaction
#   patch - save and verify a patch, then use the normal Python file writer
#   apply - verify and apply the patch through Git (no commit/push)
GIT_MODE = "off"
GIT_PATCH_DIR = None  # Optional directory for patch + JSON provenance artifacts
GIT_STAGE = False  # If GIT_MODE="apply", also stage the applied file

# Verification gate configuration
# -------------------------------
# Optional ordered command gates run on an isolated candidate copy BEFORE the
# live source file is changed. Exit code 0 means pass; any nonzero exit rejects
# the candidate. Protocol-aware tools may read HEALING_AGENT_CANDIDATE and print
# JSON detail to stdout, but the exit code decides.
VERIFY_COMMAND = None  # e.g. "pytest tests/test_loader.py" or ["python", "check.py"]
VERIFY_TIMEOUT_SECONDS = 120

# GitHub Integration
# ------------------
# Escalation for failures healing could not repair: an issue in your own
# repository turns the attempt into work an agent or a human can pick up.
# The PR delivery flow is still groundwork (see docs/apply-verify-design.md).
# SECURITY: never put a token VALUE in this file - "token_env" names the
# environment variable that holds it (or authenticate via the gh CLI).
GITHUB = {
    "repo": None,                  # "owner/name"; None = detect from the git remote
    "token_env": "GITHUB_TOKEN",   # NAME of the env var holding the token, never the value
    "issue_on_failure": False,     # open an issue when healing definitively fails
    # How much leaves the machine:
    #   reference     - error/function identity + pointers to local artifacts
    #                   (no captured values; note the exception MESSAGE is included)
    #   redacted      - also attach the redacted context JSON
    #   ai-anonymized - also attach a context JSON with values replaced by an AI pass
    "issue_detail": "reference",
    "issue_label": "healing-agent",  # label used for the issue and for deduplication
}

# Observation Configuration
# -------------------------
# Ring buffer of the application's own log records. 0 (or absent) means the
# handler is never installed: nothing is recorded and no tokens are spent.
# A positive number is how many recent records to keep AND to send to the AI
# alongside the failure. Arm it while the program is still healthy:
#     healing_agent.enable_log_capture()
# A buffer can only contain what was recorded BEFORE the failure.
# WARNING: log messages are free text, so name-based redaction cannot see
# inside them - logger.info(f"token={t}") would reach the provider.
LOG_BUFFER_SIZE = 0
LOG_BUFFER_LEVEL = "INFO"  # minimum level to record
# Where healing_agent.capture() writes snapshots; None = next to the caller.
CAPTURE_DIR = None

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
