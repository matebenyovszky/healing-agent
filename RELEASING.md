# Releasing Healing Agent

Two manual decisions, one command, and a workflow that does the rest.

## 1. Decide the version

SemVer, chosen from what the release *contains* — not from a roadmap milestone
name, and not from how big the work felt:

| The release… | Version |
|---|---|
| adds functionality, removes nothing | MINOR (`0.3.1` → `0.4.0`), including pre-1.0 |
| only fixes behavior | PATCH (`0.4.0` → `0.4.1`) |
| removes or renames a config key, import path or signature | MINOR pre-1.0, MAJOR after 1.0 — and say so at the top of the entry |

Write it in `pyproject.toml`. That is the only place the distribution version
exists; `healing_agent.__version__` reads it from package metadata.

**Only if this release adds, renames or removes a configuration key**, set
`CONFIG_SCHEMA_VERSION` in `healing_agent/_version.py` and the matching
`HEALING_AGENT_CONFIG_VERSION` in `config_template.py` to this release's
number. Leave them alone otherwise — the marker describes the config layout,
not the release, and bumping it on every version trains users to ignore the
"your config is outdated" warning.

## 2. Write the changelog entry

Turn the `## [Unreleased]` heading into `## [X.Y.Z] - YYYY-MM-DD`. Keep the
Keep a Changelog sections (`Fixed` / `Added` / `Changed`), and state what
breaks — or that nothing does — in one line under the heading.

## 3. Run the release

```bash
python scripts/release.py            # verify and build, change nothing
python scripts/release.py --publish  # then tag and push, which publishes
```

The preflight refuses to continue on: a dirty working tree, a branch other
than `main`, a `main` that differs from `origin/main`, an existing `vX.Y.Z`
tag, a changelog still marked Unreleased, a config schema marker ahead of the
release, a ruff finding, a failing test, or a build whose artifacts do not
match the declared version. Every one of those is cheap to fix now and
impossible to fix after upload, because **a PyPI version can never be reused**.

`--publish` pushes the `vX.Y.Z` tag. That tag is the trigger: the
[Publish Python Package](.github/workflows/python-publish.yml) workflow builds
from that commit, runs the tests again, and uploads to PyPI through Trusted
Publishing — short-lived OIDC credentials issued to the `release` environment,
so no API token exists to leak. Nothing is uploaded from a developer machine.

## 4. Afterwards

```bash
gh run watch --repo matebenyovszky/healing-agent   # the publish workflow
pip install healing-agent==X.Y.Z                   # in a clean venv
gh release create vX.Y.Z --title "healing-agent X.Y.Z" --notes "…"
```

A dry run is available at any time: trigger the same workflow manually
(`workflow_dispatch`) and it publishes to TestPyPI instead, with
`skip-existing`.

## If something goes wrong

- **Workflow failed before upload** — fix, commit, delete and re-push the tag
  (`git tag -d vX.Y.Z && git push --delete origin vX.Y.Z`), run the script
  again.
- **Workflow failed after a partial upload** — do not retry into the same
  version. Release a PATCH; PyPI does not allow re-uploading a version, and
  yanking is for withdrawing something published, not for replacing it.
