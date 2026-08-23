# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — releasing as 0.4.0
This release ADDS functionality and removes nothing, so SemVer makes it a MINOR
bump: `0.4.0`, not `0.3.2`. `pyproject.toml` already carries `0.4.0` so an
in-development build reports the version it will ship as. No configuration key,
import path or function signature was removed or changed.

Note on milestone naming: the roadmap's "repairs that can be trusted" milestone
was previously called "0.4". Milestone names and version numbers are now
separate — a version number follows from what a release contains, and that
milestone spans several minor releases.

### Fixed
- **The LiteLLM provider leaked its endpoint into the whole process.** It set
  `litellm.api_base`, a module-level global, so a configured API base outlived
  the call and applied to every later LiteLLM call — including calls made by
  other code sharing the interpreter. It is now passed per request
- The `openai` package is no longer imported at `ai_broker` import time. It is
  needed only by the azure and openai providers, and an Ollama-only or
  LiteLLM-only install should not fail on a package it never calls. The
  connection-error handling that referenced `openai.APIConnectionError`
  resolves it lazily and behaves exactly as before when openai is installed
- **Hint prompts leaked the capture wrapper into the model's reading of
  arguments.** Captured arguments were interpolated as the raw structure
  `{'payload': {'value': ..., 'type': 'dict'}}`, and the model was observed
  treating the wrapper keys as the argument's own keys — a live escalation
  issue contained exactly that misreading. Arguments are now rendered as
  `- name (type: T) = value`
- **Backup filenames are now unique by construction, not by clock resolution.**
  0.3.1 addressed same-second backup collisions by adding microsecond precision
  to the name, which is not a guarantee: `datetime.now()` has millisecond or
  worse granularity on Windows, so two backups taken in quick succession — a
  second repair attempt is exactly that — could still receive the identical
  name. The second copy then overwrote the first, and the first is the one
  holding the PRE-HEALING source, because a session keeps only the earliest
  backup per file. `RESTORE_ON_FAILURE` would faithfully restore the mutated
  code it exists to undo. Names are now claimed atomically with
  `O_CREAT | O_EXCL` and given a numeric suffix on collision. Caught by an
  intermittently failing regression test, which is now deterministic
- Backup names are derived with `os.path.splitext` instead of
  `replace('.py', '')`, which stripped every occurrence — `loader.python.py`
  produced a backup named `loaderthon`
- Saved AI fixes no longer report `Error type: Unknown` / `Error message:
  Unknown`. `ai_fix_saver` read `error_type` / `error_message`, but
  `capture_context` writes those fields as `type` / `message`, so every header
  in `_healing_agent_fixes/` since the feature shipped was blank
- `exception_saver.save_context()` could raise `UnboundLocalError` instead of
  returning: its `return file_path` sat after the outer `except`, so a failure
  before the path was built (a context without `error["file"]`) escaped the
  saver and replaced the application's own exception in the healing path. It
  now returns `None`, as its type hint always promised, and also returns `None`
  rather than a path to a file that could not be written
- `_repair_attempts` used a mutable `{}` as its `ContextVar` default — a single
  object shared by every context that never set it. Nothing mutated it in
  place, so no counts leaked, but the next in-place update would have leaked
  them across unrelated healing sessions. The default is now `None`
- `import healing_agent.config_template` (and any other submodule this package
  does not import itself) failed with `ImportError`. The package replaces
  itself with a callable instance in `sys.modules`, and that instance did not
  carry `__path__`, so the import system did not recognise it as a package
- **Console output can no longer replace the application's exception.** Healing
  Agent decorates its messages with `♣`, `⚕️` and `✧`, which a cp1252 console —
  the Windows default, inherited by any redirected stdout such as a scheduled
  job's log file — cannot encode. A raw `print()` raised `UnicodeEncodeError`
  from inside the healing path, and because the error branch printed too, that
  encoding error propagated *instead of* the application's own exception,
  breaking the project's central guarantee. All library output now goes through
  `healing_agent.console.emit()`, which degrades to a lossy transliteration
  rather than raising. Found by a live end-to-end run; the test suite never hit
  it because pytest captures stdout through a UTF-8 capable buffer

### Added
- **`healing_agent.capture(label=...)`: evidence without a failure.** Writes a
  redacted context snapshot of the calling frame at any point — no exception,
  no AI call, no mutation. It exposes the `error=None` path that
  `capture_context` always supported but nothing could reach. Snapshots go to
  `_healing_agent_captures/` next to the calling module, or to `CAPTURE_DIR`.
  Capturing never raises into the observed program
- **Optional ring buffer of the application's own log records.**
  `LOG_BUFFER_SIZE` (0 or absent means the handler is never installed and
  nothing is recorded) plus `healing_agent.enable_log_capture()` /
  `disable_log_capture()`. Buffered records join the captured context and both
  the fix and hint prompts, so the model sees what the program was doing before
  it broke, not only where it stopped. Level-filtered via `LOG_BUFFER_LEVEL`,
  per-record size capped, and documented as unable to redact free-text log
  messages. A buffer only holds what was recorded before the failure, so it
  must be armed at startup
- `capture_context(frame=...)` accepts an explicit frame, so a caller other
  than the decorator can snapshot the frame it actually means
- `healing_agent.__version__`, read from installed package metadata, so
  `pyproject.toml` is the only place the distribution version is written
- **Config schema compatibility is now checked and repaired on load.**
  `HEALING_AGENT_CONFIG_VERSION` was declared in the generated config file but
  never read by anything. It now marks the config SCHEMA — which keys exist —
  and is compared against `healing_agent._version.CONFIG_SCHEMA_VERSION` every
  time a config is loaded:
  - a config predating the current schema keeps working: every behavior key it
    is missing is filled in from the shipped template, and the user is told
    which ones, by name, so the file can be refreshed deliberately
  - provider credentials (`AI_PROVIDER`, `AZURE`, `OPENAI`, `ANTHROPIC`,
    `OLLAMA`, `LITELLM`) are NEVER filled in — the template holds only
    placeholders, and defaulting one would turn "no provider configured" into
    a confusing authentication error
  - a config from a NEWER install is loaded unchanged with a warning that
    unknown settings are ignored
  - the schema version is bumped only when a config key is added, renamed or
    removed — not on every release — and is then set to the release that ships
    the change, so it stays comparable with markers already on disk and stops
    declaring every existing config outdated on each patch release
- Modules a config file imports (`import os` at the top of the template) are no
  longer carried along as if they were settings
- Ruff lint gate in CI, restricted to defect-hunting rules (`E9`, `F`, `B`) so
  a failure always means something real rather than a style preference
- CodeQL analysis (`security-and-quality`) on push, pull request and weekly
- Dependabot for GitHub Actions and pip, with development dependencies grouped
  into a single pull request
- GitHub issue escalation: with `GITHUB["issue_on_failure"] = True`, a failure
  healing could not repair opens an issue in the application's own repository,
  so the attempt is not lost and an issue→PR agent or a human can answer with
  a pull request. The escalation reports the ORIGINAL application failure, not
  a later failure of the agent's own candidate
- Three issue detail levels (`GITHUB["issue_detail"]`): `reference` (default,
  no captured values leave the machine), `redacted`, and `ai-anonymized`
- Failure deduplication: an invisible fingerprint built from the exception
  type, function qualname, repository-relative path, the failing line's TEXT
  (not its number) and the exception message with digits normalized, so
  repeated occurrences do not open repeated issues. Open labelled issues are
  listed for matching rather than queried through the search API, whose
  indexing lag would leak duplicates in exactly the rapid-repeat case

- **Provider sampling parameters.** Every provider block accepts an optional
  `params` dict, forwarded to that provider verbatim: request keyword
  arguments for Azure, OpenAI, Anthropic and LiteLLM, and Ollama's `options`
  object for local models — which previously received no sampling settings at
  all, so temperature, `seed` and `num_ctx` could not be set. Nothing is
  validated or translated here: parameter names belong to the provider, and a
  whitelist would go stale with every API release. An absent or empty `params`
  produces exactly the request earlier releases sent. For Anthropic, `params`
  overrides the block-level `temperature` / `max_tokens` shorthands, so one
  config can be swept across settings without being rewritten
- **Per-session model usage ledger** (`healing_agent/usage_ledger.py`). A
  repair is several model calls — a hint, a fix, a retry — and until now
  nothing could answer what one repair cost. Each call is recorded for the
  duration of the healing session (provider, model, seconds, prompt and
  completion tokens), the totals go into the saved fix artifact, and `DEBUG`
  prints them. Deliberate limits: counts only, never prompt or completion
  text, because the artifact is meant to be shareable; a provider that reports
  no usage leaves `None` instead of a zero that would read as "free", and a
  total mixing reported and unreported calls is marked `partial`; no prices
  are baked in, since they change faster than releases
- `AI_PROVIDER` in the shipped template now reads `HEALING_AGENT_PROVIDER`
  from the environment (default unchanged), so a benchmark sweep or a
  multi-provider setup can switch providers without editing the config file
- `docs/apply-verify-design.md`: why this is not a CI healer — CI is the
  verification gate (`pr-checks`), not the surface being repaired; the
  runtime evidence a CI-triggered agent cannot see is the whole point
- `docs/benchmark.md`: the repair benchmark design — one scenario dataset
  shared with the acceptance suite, an outcome taxonomy that separates a real
  repair from a `false-fix` and a correct refusal from a `fabricated` value,
  the model × sampling-parameter × prompt-variant matrix with `pass^k`
  reliability reporting, and the four library changes it depends on

### Changed
- Nothing removed or renamed; escalation is opt-in and defaults to off.
  Escalation problems are logged and never replace the application's own
  exception

## [0.3.1] - 2026-08-23
No breaking changes: no configuration key, import path, or function signature
was removed or changed. One default BEHAVIOR change is called out below.

### Fixed
- Code backups taken within the same second no longer overwrite each other;
  backup filenames now carry microsecond precision. Previously a second
  repair attempt within the same second destroyed the backup holding the
  original pre-healing source — exactly the file needed for a rollback

### Added
- `RESTORE_ON_FAILURE` (default `True`): when healing fails definitively
  (`MAX_ATTEMPTS` exhausted, repaired module still failing, or an invalid
  candidate) the pre-healing source is restored from the healing session's
  first backup, so no half-healed file is left behind. Generated candidates
  remain available under `_healing_agent_fixes/`
- `GITHUB` configuration block as groundwork for issue escalation and the PR
  delivery flow; it stores only the NAME of the token environment variable,
  never a token value
- `docs/apply-verify-design.md`: the 0.4 propose → verify → apply pipeline
  specification (unified response envelope, verify gates, APPLY policies,
  repository-CI gate, issue escalation with privacy levels)
- `docs/apply-verify-design.md`: interoperability with issue→PR agents
  (OpenHands, SWE-agent, auto-code-rover, Copilot coding agent) — the
  escalation issue is specified as agent input rather than a human notice,
  and the same boundary works synchronously as a `PROPOSE = "command"`
  backend
- README positioning: relationship to Wolverine, to the agentless repair
  results, and to hosted products such as Sentry Seer
- ROADMAP: incident memory (make the artifact directories readable evidence
  instead of write-only exhaust), issue→PR agent interoperability, a
  `healing-agent run script.py` outside-in runner for 1.0, `APPLY="ask"`,
  a `healing-agent doctor` provider/config check, a concrete route from the
  data-drift suite to a reproducible published benchmark, and the guardrail
  that a repair may never edit the tests that judge it

### Changed
- **Behavior change (opt-out available):** a failed healing session now leaves
  the source file byte-identical to its pre-healing state instead of keeping
  the last mutated revision. Set `RESTORE_ON_FAILURE = False` to preserve the
  previous behavior and inspect the mutated file

## [0.3.0] - 2026-08-15
### Added
- **Data Healing demonstrated**: 11 live acceptance scenarios prove the heal
  loop adapts loaders to structurally drifted input while old inputs keep
  working — renamed/reordered CSV headers, reshaped API payloads, date-format
  drift, an error inside an undecorated helper, three-layer Excel workbook
  drift, mixed valid/invalid records with preserved quarantine semantics,
  UTF-8 BOM plus Hungarian decimal locale, and pagination-envelope drift
- Two anti-fabrication guardrail scenarios: a missing required column and a
  decoy numeric column must raise a clear error, never invent business data
- Drift-aware fix and hint prompts: adapt to BOTH old and new structure, map
  only same-business-concept aliases, normalize name comparisons
  (case/whitespace/diacritics), require a single-function replacement
- One bounded retry when a generated fix fails validation, with robust
  markdown fence stripping and an AST structural check
- `docs/data-healing.md` describing the prompt+tests approach, the guardrail
  story, the escalation rule (prompt → context → code), and a determinism note

### Fixed
- Function replacement no longer drops decorator arguments such as
  `@healing_agent(MAX_ATTEMPTS=5)`; original decorator lines are preserved
- A single invalid generation no longer wastes the whole repair attempt

### Changed
- README and ROADMAP slimmed around the KISS thesis: minimal transparent code,
  intelligence in the model and prompts, trust in acceptance tests

## [0.2.9] - 2026-08-13
### Added
- Optional repository-aware Git workflow with `GIT_MODE=off|patch|apply`
- Patch provenance sidecars containing source hashes, repository path, Git HEAD, language, and `git apply --check` status
- Guarded patch application that refuses stale or changed source files, with optional staging and no automatic commit/push
- Language-neutral text patch API for PowerShell, shell, JavaScript, and other script adapters
- A concrete dependency-free Data Healing protocol and acceptance design

### Changed
- `SAVE_GIT_PATCHES=True` remains supported as an alias for `GIT_MODE="patch"`

## [0.2.8] - 2026-08-13
### Added
- Optional `SAVE_GIT_PATCHES` output for minimal, reviewable unified diffs that can be consumed by `git apply` or a later pull-request workflow
- Documentation for the boundary between local Git patches and future token-based GitHub draft PR integration

### Changed
- Restored `AUTO_FIX=True` for new configurations to preserve Healing Agent's original automatic-application behavior
- Kept automatic package installation separately disabled with `AUTO_SYSCHANGE=False`
- Function replacement now changes only the supervised function instead of reformatting the complete source module
- Raised the supported Python floor to 3.10 and aligned CI with Python 3.10–3.13
- Kept Data Healing framework-level with no Docling, Fidelis, Pydantic, pandas, or domain-specific core dependency

## [0.2.7] - 2026-08-13
### Security
- Name-based secret redaction (`healing_agent/redactor.py`) applied before any
  captured context reaches an AI provider or disk; configurable via
  `REDACT_SECRETS`, `REDACT_EXTRA_PATTERNS`, `REDACT_PLACEHOLDER`
  (shipped in this release, previously unlisted)
- Healing-agent internal frame variables (provider config with API keys, raw
  args/kwargs) are no longer captured into exception context

### Added
- Regression tests for bounded repair attempts and exception propagation
- Standard pytest discovery and a CI test matrix for Python 3.9-3.13
- A staged project roadmap covering safe repair, agent failures, integrations, and cross-language support
- Optional dependency groups for development, Anthropic, and LiteLLM
- Release guidance and roadmap items for business contracts, related tests, data-schema healing, agent-health sampling, and optional GitHub integration
- A highlighted Data Healing product direction for verified Excel/PDF schema-drift adapter generation

### Changed
- `MAX_ATTEMPTS` now bounds recursive repair attempts across module reloads
- Failed or disabled healing re-raises the original application exception instead of returning `None`
- Failed repaired-module execution restores the previously loaded module
- The test runner now returns a failing exit code when pytest fails
- The overall test script no longer overwrites checked-in tests from examples
- Overall configuration validation now fails the test run instead of continuing
- New configurations default `AUTO_FIX` and `AUTO_SYSCHANGE` to `False`
- Example defaults now use `gpt-5.6-terra`, `claude-sonnet-5`, and LiteLLM's `openai/gpt-5.6-terra`; arbitrary compatible model IDs remain configurable
- Replaced the unmaintained `astor` dependency with Python's built-in `ast.unparse`
- Declared direct HTTP dependencies explicitly, bounded provider dependency major versions, and included the build backend in development dependencies
- Made the manual PyPI release helper require an explicit TestPyPI or production target
- Made the legacy GitHub release helper verify artifacts before an explicit, draft-only publish step
- Separated manual TestPyPI runs from tag-triggered PyPI publishing to prevent duplicate attestations
- Updated the release workflow to Node.js 24-based GitHub actions
- Excluded local release environments and build output from source distributions
- Raised provider and HTTP dependency baselines to current compatible versions; direct installs may use OpenAI 3 while the latest LiteLLM currently resolves OpenAI 2.x

## [0.2.6] - 2025-01-14
### Added
- Save AI generated code suggestions to a separate file
- Option to use environment variables for API keys, settings

### Changed
- Improved readme (configuration options)

## [0.2.5] - 2024-11-10
### Added
- Automatic installation of missing modules
- Configurable system prompts
- Support of environment variables for API keys

### Changed
- Config validation updated, optimized and improved

## [0.2.4] - 2024-11-10
### Added
- New test

### Changed
- Improved error context capture (preparation for v0.3.0)
- Source code verification removed (seems unnecessary)

## [0.2.3] - 2024-11-05
### Added
- Saving global and local variables to context

### Changed
- Improved readme

## [0.2.2] - 2024-11-04
### Added
- UTF-8 support on source code

### Changed
- JSON export and console output improvements

## [0.2.1] - 2024-10-31
### Added
- Better AI API error handling
- Performance optimizations in healing_agent decorator
- This changelog file

### Changed
- Minor optimizations and bug fixes
- Updated JSONDecodeError handling
- Updated diagram

## [0.2.0] - 2024-10-31
### Added
- New hints feature for better error resolution
- Enhanced handling of different exception types
- Optimized configuration system

### Changed
- Improved overall code structure
- Enhanced error handling capabilities

## [0.1.2] - 2024-10-30
### Added
- Special JSON DECODE error handling

### Changed
- Streamlined import system
- Updated decorator parameters

## [0.1.1] - 2024-10-29
### Changed
- Improved packaging configuration
- Various small updates and optimizations

## [0.1.0] - 2024-10-29
### Added
- Initial release
- Basic error handling functionality
- Core healing agent features
- Basic documentation

[0.2.1]: https://github.com/matebenyovszky/healing-agent/compare/v0.2.0...v0.2.1
[0.2.9]: https://github.com/matebenyovszky/healing-agent/compare/v0.2.8...HEAD
[0.2.8]: https://github.com/matebenyovszky/healing-agent/compare/v0.2.7...v0.2.8
[0.2.7]: https://github.com/matebenyovszky/healing-agent/compare/v0.2.6...v0.2.7
[0.2.0]: https://github.com/matebenyovszky/healing-agent/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/matebenyovszky/healing-agent/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/matebenyovszky/healing-agent/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/matebenyovszky/healing-agent/releases/tag/v0.1.0
