# Healing Agent 🩺

Healer Agent is an intelligent code assistant that catches with detailed context and fixes errors in your Python code. It leverages the power of AI to provide smart suggestions and corrections, helping you write more robust and "self-healing" code. Your program will be able to fix itself, it will have regenerative healing abilities like [Wolverine](https://github.com/biobootloader/wolverine). 

⚠️ Not intended for production use. `AUTO_FIX` and `AUTO_SYSCHANGE` default to `False`. Enabling them permits Healing Agent to modify, reload, and run code or install packages. Failed healing always re-raises the original application exception.

Goal: first actually usable autonomous coding agent in production

[Video demo on Youtube](https://youtu.be/_N1G3qBO34s)

## Features ✨

- 🚨 Automatic error detection and handling of diverse exception types
- 💡 Smart error analysis and solution suggestions (auto-generated fixing hints and code)
- 🔍 Comprehensive error analysis including exception details, stack traces, local and globalvariables and root cause identification
- 🧠 Advanced AI-powered code healing using LLMs of different providers
- 🔧 Zero-config integration with Python projects (just import and decorate)
- 💾 Robust error tracking and debugging:
  - Exception context saved to JSON (code, error details, function info and args)
  - Automatic code backups before fixes
  - Detailed analysis results and fix history
  - Quick test of fixes
- 🤖 (Optionally) Fully automated operation with minimal human intervention
- 📦 Automatic installation of missing modules

## Flagship direction: Data Healing

The most important planned capability is **Data Healing**: keeping ingestion
code aligned with changing, but still business-valid, source documents.

Examples include:

- an Excel workbook renames or reorders columns, moves the header row, changes
  a sheet name, adds merged cells, or uses a different date/decimal format;
- a PDF keeps the same business information but moves a table, changes its
  headings or layout, or requires a different extraction strategy;
- extracted rows no longer match the target Pydantic model even though the
  required information is still present under slightly different names or
  structures.

Healing Agent should profile the failing and previously valid samples, compare
them with the declared Pydantic/data contract, and propose the smallest
versioned change to the loader or a new boundary adapter. It should then replay
both sample sets, validate business invariants, and return the code diff,
mapping explanation, fixtures, and confidence evidence. It must not silently
relax the canonical model, invent required values, or overwrite the original
document. Shadow mode and human approval come before automatic activation.

This capability is planned, not implemented in 0.2.7. See the dedicated
[Data Healing roadmap](ROADMAP.md#flagship-data-healing) for incremental steps.

## How it works 🧠

```mermaid
graph TD
    A[Import healing_agent] --> B[Configuration: AI access etc.]
    B --> C[Decorate functions with healing_agent]
    C --> D[Run Code / Execute Functions]
    D -->|No problem| L[Success]
    D -->|Exception?| F[Get and Save Detailed Context]
    F --> G[Auto-generate Fixing Hints and Code with AI]
    G --> H[Test Generated Code]
    H --> I[Create backup]
    I --> J[Apply Code Fixes]
    J --> D
```

## Installation 💻

To install Healing Agent, follow these steps:

From PyPI:

```bash
pip install healing-agent
```

PIP package from GitHub:

```bash
pip install git+https://github.com/matebenyovszky/healing-agent
```

OR from source:

1. Clone the repository:
   ```bash
   git clone https://github.com/matebenyovszky/healing-agent.git
   ```

2. Navigate to the project directory:
   ```bash
   cd healing-agent
   ```

3. Install:
   ```bash
   pip install -e .
   ```
   OR run overall test to install and test functionality:
   ```bash
   python scripts/overall_test.py
   ```

## Usage 🔧

To use Healing Agent in your project, follow these steps:

1. Import the `healing_agent` decorator in your Python file:
   ```python
   import healing_agent
   ```

2. Decorate the function you want to monitor with `@healing_agent`:
   ```python
   @healing_agent
   def your_function():
       # Your code here
   ```
   You can also pass parameters to the decorator to change the behavior set in the config file:
   ```python
   @healing_agent(AUTO_FIX=False)
   def your_function():
       # Your code here
   ```

3. Run your Python script as usual. Healing Agent will automatically detect, save context and attempt to fix any errors that occur within the decorated function.

Context (and code file backup in case of auto-fix) is saved to a JSON/Python file in the same directory as your script with actual timestamp in the filename.

## Configuration ⚙️

Healing Agent uses a flexible configuration system that supports multiple AI providers and customizable settings. The configuration is managed through a `healing_agent_config.py` file, which can be located in two places:

1. **Local Project Directory**: Healing Agent first checks for a config file in your project's directory
2. **User Home Directory**: If no local config is found, it looks for `~/.healing_agent/healing_agent_config.py`

### Configuration File Creation

The configuration file is automatically created in one of two ways:

1. **Auto-Creation**: When you first run Healing Agent, if no configuration file exists, it will:
   - Create a `.healing_agent` directory in your home folder
   - Copy the template configuration to `~/.healing_agent/healing_agent_config.py`
   - Print a message indicating where the new config file was created

2. **Manual Creation**: You can manually create the configuration file:
   - Copy `healing_agent/config_template.py` from the package
   - Rename it to `healing_agent_config.py`
   - Place it in either your project directory or `~/.healing_agent/`
   - Update the AI provider settings and other options

### Configuration Options

The configuration file includes:

1. **AI Provider Selection**: Choose from supported providers:
   - OpenAI
   - Azure OpenAI
   - LiteLLM
   - Anthropic
   - Ollama

2. **Provider Credentials**: Set up API keys and endpoints
   - Can be defined directly in the config file
   - Can be loaded from environment variables (recommended)

3. **Behavior Settings**:
   ```python
   MAX_ATTEMPTS = 3       # Hard limit across recursive repair/reload attempts
   DEBUG = True           # Enable detailed logging
   AUTO_FIX = False       # Opt in to applying and executing generated fixes
   AUTO_SYSCHANGE = False # Opt in to automatic package installation
   BACKUP_ENABLED = True # Create backups before fixes
   ```

`MAX_ATTEMPTS` counts repair cycles for the same decorated function, including
calls reached after a repaired module is reloaded. For example, a value of `3`
allows at most three generated-and-applied repair attempts. It is not a general
retry setting for every provider or network error; those failures stop healing
and the original application exception is raised.

If a repaired module cannot be loaded or its top-level code fails, Healing Agent
restores the previous module object in `sys.modules`. This protects the running
process, but does not revert the edited source file. Keep `BACKUP_ENABLED=True`
and use version control so source changes remain recoverable.

### Automatic system changes

`AUTO_SYSCHANGE=True` currently recognizes missing-module errors and invokes
the active interpreter as `python -m pip install <inferred-package>`. It has no
package allowlist, version pinning, approval step, or package-confusion defense,
so it should only be used in a disposable development environment. It defaults
to `False`; the roadmap replaces direct installation with a reviewable,
policy-controlled dependency proposal.

Example configuration for Azure OpenAI:
```python
AI_PROVIDER = "azure"

AZURE = {
    "api_key": os.getenv("AZURE_API_KEY"),  # Recommended: use environment variable
    "endpoint": "https://your-resource.openai.azure.com",
    "deployment_name": "gpt-4",
    "api_version": "2024-02-01"
}
```

The model name is configurable and is not restricted to a hard-coded list. The OpenAI example defaults to `gpt-5.6-terra`, while Azure uses your deployment name. Provider/model combinations still need a published compatibility test matrix; see the [roadmap](ROADMAP.md).

Anthropic and LiteLLM support are optional extras (`pip install
"healing-agent[anthropic]"` or `pip install "healing-agent[litellm]"`). The
current LiteLLM extra requires Python 3.10 or newer; the core package continues
to support Python 3.9. The 0.2.7 dependency baselines are OpenAI 2.20.0,
Anthropic 0.121.0, LiteLLM 1.96.2, HTTPX 0.28.1, and Requests 2.34.2, with
compatible updates allowed inside the declared major range. A normal install
currently resolves to OpenAI 3.0.0. LiteLLM 1.96.2 requires OpenAI
`>=2.20,<3`, so installing the LiteLLM extra intentionally resolves to the
latest compatible OpenAI 2.x instead; the two latest releases cannot coexist
until LiteLLM adds OpenAI 3 support.

## Testing 🧪

Run the isolated regression suite with:

```bash
python -m pytest
```

`python scripts/test_runner.py` is an equivalent wrapper and returns pytest's failing exit status. `python scripts/overall_test.py` additionally builds and installs the package before running the tests.

Maintainers should follow the guarded [release checklist](RELEASING.md) before
creating a version tag or publishing to PyPI.

## Roadmap 🗺️

See [ROADMAP.md](ROADMAP.md) for small release steps toward verified repair, LLM and agent failure recovery, harness integrations such as Hermes Agent, and a language-neutral repair coordinator.

Healing Agent does not currently connect runtime failures to GitHub issues or
pull requests. The repository contains release automation, while an optional,
disabled-by-default GitHub App/Action that can open evidence-backed draft repair
PRs is planned in the roadmap.

## Use Cases 💡

- **Development**: Use Healing Agent during development to catch and fix errors early, and let AI generate fixes for your code. This is what you would do anyways, but now it's automated. 😁
- **Educational Tool**: Use Healing Agent as a learning tool to understand AI coding capabilities and limitations.

## Cooking open source 🍳

Healing Agent is distributed under the MIT License. See `LICENSE` for more information. Feedback and contributions are welcome!
