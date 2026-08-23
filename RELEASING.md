# Releasing Healing Agent

Publishing is intentionally separate from normal development commands. Never
reuse a version already uploaded to PyPI or TestPyPI.

## Release checklist

1. Confirm the working tree contains only the intended release changes.
2. Update the version in `pyproject.toml` and add the dated changelog entry.
   `pyproject.toml` is the ONLY place the distribution version is written;
   `healing_agent.__version__` reads it from installed package metadata.
   Choose the number from the content, per SemVer: a release that adds
   functionality is a MINOR bump even while the project is pre-1.0. Roadmap
   milestone names are not version numbers.
3. If — and only if — this release adds, renames or removes a configuration
   key, bump `CONFIG_SCHEMA_VERSION` in `healing_agent/_version.py` and the
   matching `HEALING_AGENT_CONFIG_VERSION` in `config_template.py` to this
   release's number. `tests/test_version.py` fails if the two disagree.
   Leave both untouched when the configuration is unchanged: the marker
   describes the config layout, not the release.
4. Run `python -m ruff check .` and `python -m pytest`.
5. Run `python -m build` and `python -m twine check dist/*`.
6. Manually run the **Publish Python Package** GitHub workflow on the release
   commit. A branch dispatch publishes to TestPyPI only.
7. Install the exact version from TestPyPI in a clean virtual environment and
   run an import/smoke test.
8. Create and push the signed or annotated `vX.Y.Z` tag only after reviewing
   the TestPyPI result. A version tag runs the checks and publishes to both
   TestPyPI (`skip-existing`) and production PyPI.
9. Verify the PyPI page and wheel install, then create the GitHub release notes.

The workflow expects Trusted Publishing to be configured for the GitHub
`release` environment on both package indexes. The legacy local helper requires
an explicit target:

```bash
python scripts/pypi_release.py test
python scripts/pypi_release.py prod  # production; use only after TestPyPI
```

Prefer the GitHub workflow because it uses short-lived OIDC credentials instead
of long-lived API tokens.

The legacy GitHub asset helper is dry-run/build-only unless `--publish` is
passed. Publish mode requires an existing version tag and creates a draft
prerelease after tests, build, and metadata checks succeed:

```bash
python scripts/github_package_upload.py
python scripts/github_package_upload.py --publish
```
