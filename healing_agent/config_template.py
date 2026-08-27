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
HEALING_AGENT_CONFIG_VERSION = "0.5.0"
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
# Optional ordered command gates run BEFORE the live source file is changed.
# Exit code 0 accepts the candidate; any nonzero exit rejects it. Protocol-aware
# tools may read HEALING_AGENT_CANDIDATE and print JSON detail to stdout, but
# the exit code decides. A command that cannot start is treated as a
# configuration error, not as a rejected candidate.
#
# SCOPE: the gate runs in a temporary directory containing the candidate FILE
# alone, with the repair applied. A self-contained checker works; a
# project-level test run (e.g. pytest over your test directory) does not, since
# the rest of the project is not there. Full-project isolation is on the roadmap.
#
#   one gate      : ["python", "checks/verify_loader.py"]
#   ordered gates : [["python", "checks/verify_loader.py"], ["ruff", "check"]]
VERIFY_COMMAND = None
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
    # How much leaves the machine. One redaction policy applies to all three -
    # they differ in how much of the evidence is attached, not in how safe it is:
    #   reference     - error/function identity + pointers to local artifacts
    #                   (no captured values; note the exception MESSAGE is included)
    #   redacted      - also attach the redacted context JSON (default: an issue
    #                   an agent or a human can act on without the machine)
    #   ai-anonymized - also attach a context JSON with values replaced by an AI pass
    "issue_detail": "redacted",
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
# Where Healing Agent's OWN messages go. Records are sent to the standard
# logger "healing_agent", which is never configured by the library, so your
# application's level, handlers, formatters and filters apply to them through
# the normal logger hierarchy.
#   auto    - use the logger when your application configured logging for it,
#             print to the console when it did not (previous behavior)
#   logging - always use the logger, even with no handler attached
#   print   - always print, whatever your application configured
LOG_MODE = "auto"
# Where healing_agent.capture() writes snapshots; None = next to the caller.
CAPTURE_DIR = None

# Evidence Configuration
# ----------------------
# The same failure context travels to three places with different economics.
# Redaction is NOT what varies: one policy runs before anything leaves the
# capture, so the evidence is equally safe everywhere. A sink only chooses how
# much of it is worth carrying.
#
#   a number = include this section with this limit; 0 or missing = leave it out
#   variables / environment / arguments : characters per VALUE. Every entry is
#       kept and trimmed on its own, so one huge dataframe cannot push the rest
#       of the state out of the report.
#   logs : number of most recent LINES
#
# The error, the traceback and the function's own source are never optional:
# a repair prompt without the source cannot produce a repair.
EVIDENCE = {
    # An artifact meant to be searched later - space is nearly free.
    "disk":     {"arguments": 3000, "variables": 3000, "environment": 3000, "logs": 500},
    # A prompt, paid for by the token, on every nested repair attempt.
    "provider": {"arguments": 1000, "variables": 400,  "environment": 300,  "logs": 50},
    # A GitHub body with a hard size limit, read by a human.
    "issue":    {"arguments": 300,  "variables": 300,  "environment": 300,  "logs": 50},
}
# Which environment variables to capture. An ALLOWLIST, not a filter: the
# environment is the most secret-dense structure in a process, and a denylist
# can only mask the secret shapes it already knows, so a bespoke secret under a
# harmless name would travel. Naming what you want inverts that. The name and
# value filters still run on top, so an allowlisted DATABASE_URL keeps its host
# and path while its password is masked. Empty list = capture nothing.
ENVIRONMENT_VARS = [
    "APP_ENV", "ENVIRONMENT", "DEPLOY_ENV", "STAGE",   # which deployment
    "TZ", "LANG", "LC_ALL",                            # which locale
    "CI", "RUNNER_OS", "CONTAINER", "KUBERNETES_SERVICE_HOST",  # where it ran
]

# Per-value ceiling applied at CAPTURE time, before any sink sees the context.
# It bounds what the process holds in memory; a sink trims further from there.
CAPTURE_VALUE_CHARS = 3000

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
