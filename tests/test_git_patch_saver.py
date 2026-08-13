from pathlib import Path
import importlib.util
import subprocess

from healing_agent.code_replacer import build_replacement_source
from healing_agent.git_patch_saver import save_git_patch


def _context(source_path: Path) -> dict:
    return {
        "error": {"file": str(source_path)},
        "function_info": {"name": "calculate"},
        "fixed_code": (
            "@healing_agent\n"
            "def calculate(value):\n"
            "    return value * 2\n"
        ),
    }


def test_replacement_is_minimal_and_does_not_write_source(tmp_path):
    source_path = tmp_path / "service.py"
    original = (
        "from healing_agent import healing_agent\n\n"
        "@healing_agent\n"
        "def calculate(value):\n"
        "    return value / 0\n\n"
        "UNCHANGED = 'keep formatting'\n"
    )
    source_path.write_text(original, encoding="utf-8")

    context = _context(source_path)
    replacement = build_replacement_source(context, context["fixed_code"])

    assert replacement is not None
    old_source, new_source = replacement
    assert old_source == original
    assert "return value * 2" in new_source
    assert "UNCHANGED = 'keep formatting'" in new_source
    assert source_path.read_text(encoding="utf-8") == original


def test_save_git_patch_creates_git_apply_compatible_artifact(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    source_path = repo / "src" / "service.py"
    source_path.parent.mkdir()
    source_path.write_text(
        "from healing_agent import healing_agent\n\n"
        "@healing_agent\n"
        "def calculate(value):\n"
        "    return value / 0\n",
        encoding="utf-8",
    )

    patch_path = save_git_patch(_context(source_path))

    assert patch_path is not None
    patch = Path(patch_path).read_text(encoding="utf-8")
    assert patch.startswith("diff --git a/src/service.py b/src/service.py\n")
    assert "--- a/src/service.py" in patch
    assert "+++ b/src/service.py" in patch
    assert "-    return value / 0" in patch
    assert "+    return value * 2" in patch
    assert source_path.read_text(encoding="utf-8").endswith("return value / 0\n")

    check = subprocess.run(
        ["git", "apply", "--check", patch_path],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stderr


def test_new_configuration_keeps_automatic_fixing_as_default():
    template_path = (
        Path(__file__).parents[1] / "healing_agent" / "config_template.py"
    )
    spec = importlib.util.spec_from_file_location("config_template_test", template_path)
    assert spec is not None and spec.loader is not None
    config_template = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_template)

    assert config_template.AUTO_FIX is True
    assert config_template.AUTO_SYSCHANGE is False
    assert config_template.SAVE_GIT_PATCHES is False
