# Healing Agent 🩺

Healing Agent is a deliberately small code-healing library: decorate a Python function, and when it raises, an AI analyzes the full context, generates a fix, backs up the original, applies the repair, and re-runs your code — like [Wolverine](https://github.com/biobootloader/wolverine), with regenerative healing abilities.

**The thesis:** a thin, transparent, minimal codebase + a capable AI + strong acceptance tests can heal recurring IT failures — broken code *and* drifting data alike. Intelligence lives in the model and the prompts; trust lives in the tests.

⚠️ Not intended for production use. `AUTO_FIX` defaults to `True` to preserve the original autonomous behavior: a generated fix can modify, reload, and run supervised code. `AUTO_SYSCHANGE` defaults to `False` because it installs packages. Set `AUTO_FIX=False` for proposal-only operation. Failed healing always re-raises the original application exception.

[Video demo on Youtube](https://youtu.be/_N1G3qBO34s)

## Features ✨

- 🚨 Automatic error detection with rich context capture (source, args, variables, traceback)
- 💡 AI-generated fixing hints and repaired code, multi-provider (Azure OpenAI, OpenAI, Anthropic, Ollama, LiteLLM)
- 📊 **Data Healing**: adapts loaders to structurally drifted input while old inputs keep working (see below)
- 🔎 **Observation without a failure**: `capture()` snapshots variables at any point, and an optional ring buffer feeds your own recent log records into the repair context
- 🔒 Secret redaction before anything is sent to a provider or written to disk
- 💾 Backups before every fix, exception context saved to JSON, optional reviewable `git apply` patches
- 🔧 Zero-config integration: import, decorate, run

## Data Healing 📊

Sometimes the code is fine but the world changed: a CSV renames or reorders its
columns, an API renests its fields, a date format flips. Healing Agent adapts
the loader so that **both the old and the new format keep working** — it does
not simply rewrite the code for the new shape.

This is live-demonstrated by acceptance tests ([tests/test_data_drift.py](tests/test_data_drift.py)),
where a scenario only passes if the healed source returns the identical
business result for the old **and** the new input:

| Scenario | Drift | Status |
|---|---|---|
| CSV renamed headers | `amount` → `osszeg` (translated headers) | ✅ healed |
| CSV reordered columns | index-based `row[2]` parsing broke | ✅ healed |
| API payload reshaped | `data.items[].name/price` → `result.records[].title/amount` | ✅ healed |
| Date format drift | `2026-01-15` → `15.01.2026` | ✅ healed |
| Error inside an undecorated helper | fix must adapt at the decorated boundary | ✅ healed |
| Excel workbook drift (3 layers) | sheet renamed + title rows above header + translated headers | ✅ healed |
| Mixed valid/invalid records | header drift healed while quarantine semantics preserved | ✅ healed |
| BOM + decimal locale | UTF-8 BOM on first header + `"1 200,50"` Hungarian numbers | ✅ healed |
| Pagination envelope | flat `items[]` → per-page `pages[].results[]`, aggregated across pages | ✅ healed |
| Required column missing entirely | must raise, not fabricate | ✅ guarded |
| Missing column + decoy numeric column | must not repurpose order numbers as amounts | ✅ guarded |

Before/after excerpt from an actual healed run (reordered-columns scenario):

```python
# before healing: hardcoded column order
total += int(row[2])

# after healing (generated): header-aware alias mapping
aliases = {"amount": ["amount", "total", "price", "value"], ...}
header_map[key] = headers.index(name)
total += int(row[header_map["amount"]])
```

**Guardrail:** when required business data is genuinely missing, the healed
code raises a clear error instead of inventing values — even when a tempting
decoy column is present. Our adversarial test caught the model summing order
numbers as amounts; two targeted prompt sentences fixed it, and the test keeps
it fixed.

The implementation is intentionally tiny: drift awareness lives in the fix and
hint prompts, correctness lives in the acceptance tests. See
[docs/data-healing.md](docs/data-healing.md) for the approach and how to extend it.

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

## Where this fits 🧭

Healing Agent is a **maintained successor to [Wolverine](https://github.com/biobootloader/wolverine)** — the project that demonstrated LLM-driven self-healing and then stopped: no commit since March 2024, 27 open issues and 10 unmerged pull requests, no published package. Its issue tracker reads as a list of things this project already does:

| Asked for in Wolverine | Healing Agent |
|---|---|
| [#52](https://github.com/biobootloader/wolverine/issues/52), [#41](https://github.com/biobootloader/wolverine/issues/41) — an installable, system-wide package | `pip install healing-agent`, Python 3.10–3.13 |
| [#1](https://github.com/biobootloader/wolverine/issues/1) — get the failing function's variable values into the prompt | context capture includes `function_arguments`, `locals` and `traceback_frames` by default |
| [#40](https://github.com/biobootloader/wolverine/issues/40) — validate that a fix really changes something, to prevent loops | bounded attempts (`MAX_ATTEMPTS`) plus `compile()` and single-function AST checks before a candidate is accepted |
| [#23](https://github.com/biobootloader/wolverine/issues/23) — better error handling, do not apply blindly | `AUTO_FIX=False` proposal-only mode, `RESTORE_ON_FAILURE` rollback, and the original exception always re-raised |
| [#19](https://github.com/biobootloader/wolverine/issues/19) — GitHub Actions integration | planned as the `pr-checks` verify gate and `APPLY="pr"` ([ROADMAP.md](ROADMAP.md)) |

Wolverine rewrote a whole script through line-numbered JSON edit operations; Healing Agent replaces exactly one decorated function, backs it up first, and restores it when healing fails.

**Why the codebase stays small.** [Agentless](https://github.com/OpenAutoCoder/Agentless) reported that a fixed localize → repair → validate pipeline — no agent loop, no tool-choosing LLM — outperformed the open-source software agents on SWE-bench Lite (32.00%) at roughly $0.70 per issue. That is external evidence for the thesis above: complexity belongs in verification, not in scaffolding.

**Not a CI healer — the inverse.** "CI went red, let an agent fix it and open a PR" is a crowded space, and coding agents are on home ground there: CI hands them a repository, a diff and a log. None of them can see the running process. Healing Agent's ground is the 02:00 scheduled job — no pull request, no reviewer, no agent watching, just an exception and the values that were in memory when it happened. CI is not what we repair, it is what we *verify against*: the repository's own test suite is the gate a runtime-derived fix has to pass ([docs/apply-verify-design.md](docs/apply-verify-design.md)).

**Compared to hosted products.** [Sentry Seer Autofix](https://sentry.io/product/seer/autofix/) solves the neighbouring problem commercially, and solves it well: production telemetry in, root cause and a pull request out. It is a hosted service, though, and your errors have to reach it. Healing Agent is MIT-licensed, runs inside your own process with your own provider (Azure OpenAI, OpenAI, Anthropic, Ollama, LiteLLM), redacts secrets before anything leaves the machine, and needs no backend at all. It also sees what a telemetry pipeline cannot: the actual argument and local-variable values at the moment of the failure.

## Installation 💻

```bash
pip install healing-agent
```

From GitHub or source:

```bash
pip install git+https://github.com/matebenyovszky/healing-agent
# or
git clone https://github.com/matebenyovszky/healing-agent && cd healing-agent && pip install -e .
```

Anthropic and LiteLLM support are optional extras: `pip install "healing-agent[anthropic]"` or `"healing-agent[litellm]"`. Python 3.10–3.13 is supported. Note: LiteLLM currently pins OpenAI `<3`, so the LiteLLM extra resolves to the latest OpenAI 2.x.

## Usage 🔧

```python
import healing_agent

@healing_agent
def your_function():
    ...

# or override config per function:
@healing_agent(AUTO_FIX=False)
def your_function():
    ...
```

Run your script as usual. On an exception, Healing Agent captures context, generates and (by default) applies a fix, and re-executes. Context, backups, and fixes are saved next to your script in `_healing_agent_*` folders.

### Observing without a failure

The same evidence that powers a repair is useful on its own — knowing every variable at the moment an API call returned something unexpected is often the whole debugging session:

```python
response = requests.get(url)
healing_agent.capture("supplier response")   # redacted snapshot, no AI call, no mutation
```

Snapshots land in `_healing_agent_captures/` next to the calling module (or `CAPTURE_DIR`). Secret redaction applies here too, and capturing never raises into your program.

Optionally, Healing Agent can also keep the last N of your **own log records** and include them in the repair context — the stack trace says where the program broke, the log says what it was doing:

```python
LOG_BUFFER_SIZE = 50          # in your config; 0 or absent = never installed
```

```python
healing_agent.enable_log_capture()   # arm it at startup, while the program is healthy
```

A ring buffer can only hold what was recorded *before* the failure, so it has to be armed early; `healing_agent.disable_log_capture()` removes it again. Records are level-filtered (`LOG_BUFFER_LEVEL`) and individually length-capped, and lowering `LOG_BUFFER_SIZE` immediately lowers how many are sent.

⚠️ Log messages are free text, so name-based redaction cannot see inside them — `logger.info(f"token={t}")` would reach the provider. Keep it off unless you trust your log messages.

**What is *not* sent:** the captured `variables` block (locals and globals — about 2.5 KB of a typical 8 KB context) is saved to disk but deliberately never included in a prompt, because it would roughly double the ~990-token fix prompt on every nested attempt. Giving the model tools to *request* specific variables or log lines instead is [ROADMAP](ROADMAP.md) item 7.

## Configuration ⚙️

Configuration lives in `healing_agent_config.py` — first looked up in your project directory, then in `~/.healing_agent/`. On first run a template is copied there automatically; edit it (or use environment variables, recommended for keys).

Key settings:

```python
AI_PROVIDER = "azure"     # azure | openai | anthropic | ollama | litellm

MAX_ATTEMPTS = 3          # Hard limit across recursive repair/reload attempts
DEBUG = True              # Detailed logging
AUTO_FIX = True           # Apply and execute generated fixes
AUTO_SYSCHANGE = False    # Never install packages automatically (keep False)
BACKUP_ENABLED = True     # Back up sources before fixes
RESTORE_ON_FAILURE = True # Roll the source back when healing definitively fails
SAVE_EXCEPTIONS = True    # Save exception context JSON
REDACT_SECRETS = True     # Redact secrets before AI/disk (keep True)
GIT_MODE = "off"          # off | patch (save reviewable diff) | apply (guarded git apply)

# Observation (see "Observing without a failure" above)
LOG_BUFFER_SIZE = 0       # 0 or absent = ring buffer never installed; N = keep and send N records
LOG_BUFFER_LEVEL = "INFO" # Minimum level the buffer records
CAPTURE_DIR = None        # Where capture() writes; None = next to the calling module
```

Provider example (Azure OpenAI):

```python
AZURE = {
    "api_key": os.getenv("AZURE_API_KEY"),   # recommended: environment variable
    "endpoint": "https://your-resource.openai.azure.com",
    "deployment_name": "gpt-4o-mini",
    "api_version": "2024-02-01",
}
```

Model IDs are configurable, not hardcoded. If a repaired module fails to load, the previous module object is restored in `sys.modules`. When healing fails definitively — `MAX_ATTEMPTS` exhausted, or the repaired module still failing — `RESTORE_ON_FAILURE=True` (the default) also rolls the **source file** back to its pre-healing state, so no half-healed code is left behind; the generated candidate stays available under `_healing_agent_fixes/`. Set it to `False` to keep the mutated file for inspection.

### Sampling parameters and comparing models

Every provider block takes an optional `params` dict, forwarded to that provider **verbatim** — request keyword arguments for Azure, OpenAI, Anthropic and LiteLLM, and Ollama's `options` object for local models. Nothing is validated or translated: parameter names belong to the provider. Leave it empty and the request is exactly what earlier releases sent.

```python
OLLAMA = {
    "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    "model": os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
    "timeout": 300,                       # local models are slower than APIs
    "params": {"temperature": 0.2, "seed": 7, "num_ctx": 8192},
}
```

`AI_PROVIDER` reads `HEALING_AGENT_PROVIDER` from the environment, so the same config can be swept across providers without being edited:

```bash
HEALING_AGENT_PROVIDER=ollama OLLAMA_MODEL=qwen2.5-coder:32b python -m pytest tests/test_data_drift.py -v
```

With `DEBUG = True` each healing session reports what it spent — `♣ Model usage: 3 model call(s), 41.2s, tokens in/out: 5120/860` — and the same summary is written into the saved fix artifact. Only counts are recorded, never prompts. If a repair fails on a small local model, rule out a too-small `num_ctx` (which truncates the captured evidence silently) before concluding the model cannot do it. See [docs/benchmark.md](docs/benchmark.md) for the planned model × parameter × prompt matrix.

### Reviewable Git patches (optional)

Git is never required and nothing is ever committed or pushed. `GIT_MODE="patch"` saves each valid fix as a minimal unified diff plus a JSON provenance sidecar (repo root, source hashes, Git HEAD, language, verification state) under `_healing_agent_fixes/` — reviewable with `git apply --check`. `GIT_MODE="apply"` additionally applies the patch through Git after re-checking the source hash. The patch layer is language-neutral (`save_text_patch(...)` works for PowerShell, shell, JS, etc.); the decorator itself is Python-only.

### Automatic system changes

`AUTO_SYSCHANGE=True` pip-installs inferred missing modules with no allowlist or pinning — use only in disposable environments. It defaults to `False`.

## Testing 🧪

```bash
python -m pytest
```

Live data-healing acceptance tests skip automatically when no AI provider is configured, so CI stays green. `python scripts/overall_test.py` additionally builds and installs the package first. Maintainers: follow [RELEASING.md](RELEASING.md) before tagging.

## Roadmap 🗺️

See [ROADMAP.md](ROADMAP.md) for the path toward verified repairs, agent/LLM failure healing, and harness integrations. Runtime healing never reads or requires a GitHub token; commits, branches, and PRs remain explicit host-level steps.

## Use Cases 💡

- **Development**: catch and fix errors early, automated — this is what you would do anyway. 😁
- **Data ingestion**: keep loaders aligned with drifting sources (renamed columns, reshaped APIs) under test-enforced guardrails.
- **Education**: explore AI coding capabilities and their limits.

## Cooking open source 🍳

MIT License. Feedback and contributions are welcome!
