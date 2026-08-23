"""Version and config-schema consistency.

Version numbers live in exactly two places and each has an owner:

* ``pyproject.toml`` owns the distribution version; ``healing_agent.__version__``
  only reflects it, through installed package metadata.
* ``healing_agent._version.CONFIG_SCHEMA_VERSION`` owns the config schema
  version; ``config_template.py`` only stamps it into generated config files.

Nothing enforces either link at runtime, so these tests do. A half-finished
version bump is otherwise invisible until a release is already published.
"""

import re
from pathlib import Path

import pytest

from healing_agent import _version
from healing_agent import config_loader, config_template

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


@pytest.fixture(autouse=True)
def _fresh_schema_notices():
    """Notices are emitted once per process; each test gets a clean slate."""
    config_loader._reported_schemas.clear()
    yield
    config_loader._reported_schemas.clear()


def _pyproject_version():
    if not PYPROJECT.exists():  # installed wheel, not a source checkout
        pytest.skip("pyproject.toml is not part of an installed distribution")
    match = re.search(
        r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match, "pyproject.toml has no [project] version"
    return match.group(1)


def test_config_template_stamps_the_declared_schema_version():
    assert config_template.HEALING_AGENT_CONFIG_VERSION == _version.CONFIG_SCHEMA_VERSION, (
        "config_template.py and _version.CONFIG_SCHEMA_VERSION disagree; a "
        "config key was added or removed without bumping both"
    )


def test_schema_version_never_leads_the_distribution_version():
    # The schema version names the release that last changed the config layout,
    # so it can lag the distribution version but must never run ahead of it.
    assert _version.parse_version(
        _version.CONFIG_SCHEMA_VERSION
    ) <= _version.parse_version(_pyproject_version())


def test_installed_version_matches_pyproject_when_installed():
    if _version.__version__ == "0.0.0.dev0":
        pytest.skip("healing_agent is not installed; metadata is unavailable")
    if _version.__version__ != _pyproject_version():
        pytest.skip(
            "editable install predates the current pyproject version; "
            "reinstall with `pip install -e .` to re-check"
        )
    assert _version.__version__ == _pyproject_version()


def test_version_is_reachable_from_the_package():
    import healing_agent

    assert healing_agent.__version__ == _version.__version__
    assert healing_agent.CONFIG_SCHEMA_VERSION == _version.CONFIG_SCHEMA_VERSION


@pytest.mark.parametrize(
    "value, expected",
    [
        ("0.4.0", (0, 4, 0)),
        ("0.3.1", (0, 3, 1)),
        ("1.0", (1, 0)),
        ("0.4.0.dev0", (0, 4, 0)),  # a pre-release suffix adds no component
        ("0.4.0rc1", (0, 4, 0)),
        ("", ()),
        (None, ()),
        (3, ()),
        ("not-a-version", ()),
    ],
)
def test_parse_version(value, expected):
    assert _version.parse_version(value) == expected


def test_unparseable_version_sorts_before_every_real_one():
    assert _version.parse_version("garbage") < _version.parse_version("0.0.1")


def test_older_config_is_completed_from_the_template(capsys):
    # A config written before GITHUB and RESTORE_ON_FAILURE existed.
    old = {
        "HEALING_AGENT_CONFIG_VERSION": "0.2.8",
        "AI_PROVIDER": "openai",
        "OPENAI": {"api_key": "user-key"},
        "MAX_ATTEMPTS": 7,
    }

    reconciled = config_loader.reconcile_config_schema(old)

    assert reconciled["MAX_ATTEMPTS"] == 7, "user settings must never be overwritten"
    assert reconciled["OPENAI"] == {"api_key": "user-key"}
    assert reconciled["RESTORE_ON_FAILURE"] is True
    assert "GITHUB" in reconciled and reconciled["GITHUB"]["issue_on_failure"] is False
    assert reconciled["HEALING_AGENT_CONFIG_VERSION"] == "0.2.8", (
        "an outdated config must not be relabelled as current"
    )

    message = capsys.readouterr().out
    assert "0.2.8" in message and _version.CONFIG_SCHEMA_VERSION in message
    assert "RESTORE_ON_FAILURE" in message


def test_credentials_are_never_filled_in_from_the_template():
    # A missing provider block must stay missing: a placeholder key would turn
    # "you have not configured a provider" into a confusing auth error.
    minimal = {"HEALING_AGENT_CONFIG_VERSION": "0.2.8", "AI_PROVIDER": "openai"}

    reconciled = config_loader.reconcile_config_schema(minimal)

    for provider in ("AZURE", "OPENAI", "ANTHROPIC", "OLLAMA", "LITELLM"):
        assert provider not in reconciled
    assert reconciled["AI_PROVIDER"] == "openai"


def test_unversioned_config_is_treated_as_outdated(capsys):
    reconciled = config_loader.reconcile_config_schema({"AI_PROVIDER": "openai"})

    assert reconciled["MAX_ATTEMPTS"] == config_template.MAX_ATTEMPTS
    assert "unversioned" in capsys.readouterr().out


def test_current_config_is_passed_through_untouched(capsys):
    current = {
        "HEALING_AGENT_CONFIG_VERSION": _version.CONFIG_SCHEMA_VERSION,
        "AI_PROVIDER": "openai",
    }

    reconciled = config_loader.reconcile_config_schema(dict(current))

    assert reconciled == current, "a current config must not gain keys"
    assert capsys.readouterr().out == "", "a current config must not warn"


def test_newer_config_warns_but_still_loads(capsys):
    newer = {"HEALING_AGENT_CONFIG_VERSION": "99.0.0", "AI_PROVIDER": "openai"}

    reconciled = config_loader.reconcile_config_schema(dict(newer))

    assert reconciled == newer, "settings from a newer config must be left alone"
    assert "NEWER" in capsys.readouterr().out


def test_the_schema_notice_is_emitted_once_per_process(capsys):
    # load_config() runs on every healing attempt; a repeatedly failing job
    # must not have its log filled with the same advice about a file.
    old = {"HEALING_AGENT_CONFIG_VERSION": "0.2.8", "AI_PROVIDER": "openai"}

    config_loader.reconcile_config_schema(dict(old))
    assert capsys.readouterr().out != ""

    config_loader.reconcile_config_schema(dict(old))
    assert capsys.readouterr().out == ""


def test_config_settings_never_include_imported_modules():
    # `import os` at the top of the template is not a setting.
    defaults = config_loader.load_template_defaults()

    assert "os" not in defaults
    assert "MAX_ATTEMPTS" in defaults
