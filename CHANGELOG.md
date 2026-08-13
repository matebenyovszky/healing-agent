# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.8] - Unreleased
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
[0.2.8]: https://github.com/matebenyovszky/healing-agent/compare/v0.2.7...HEAD
[0.2.7]: https://github.com/matebenyovszky/healing-agent/compare/v0.2.6...v0.2.7
[0.2.0]: https://github.com/matebenyovszky/healing-agent/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/matebenyovszky/healing-agent/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/matebenyovszky/healing-agent/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/matebenyovszky/healing-agent/releases/tag/v0.1.0
