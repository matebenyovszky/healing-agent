# Releasing Healing Agent

Publishing is intentionally separate from normal development commands. Never
reuse a version already uploaded to PyPI or TestPyPI.

## Release checklist

1. Confirm the working tree contains only the intended release changes.
2. Update the version in `pyproject.toml` and add the dated changelog entry.
3. Run `python -m pytest`.
4. Run `python -m build` and `python -m twine check dist/*`.
5. Manually run the **Publish Python Package** GitHub workflow on the release
   commit. A branch dispatch publishes to TestPyPI only.
6. Install the exact version from TestPyPI in a clean virtual environment and
   run an import/smoke test.
7. Create and push the signed or annotated `vX.Y.Z` tag only after reviewing
   the TestPyPI result. A version tag runs the checks and publishes to both
   TestPyPI (`skip-existing`) and production PyPI.
8. Verify the PyPI page and wheel install, then create the GitHub release notes.

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
