# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Fixed
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
