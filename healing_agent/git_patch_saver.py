import datetime
import difflib
from pathlib import Path
from typing import Optional

from .code_replacer import build_replacement_source


def _repository_relative_path(source_path: Path) -> Path:
    """Return a stable Git-style path when the source is inside a repository."""
    for parent in (source_path.parent, *source_path.parents):
        if (parent / ".git").exists():
            return source_path.relative_to(parent)
    return Path(source_path.name)


def save_git_patch(context: dict) -> Optional[str]:
    """Save a generated function replacement as a reviewable unified diff."""
    try:
        source_path = Path(context["error"]["file"]).resolve()
        replacement = build_replacement_source(context, context["fixed_code"])
        if replacement is None:
            return None
        original_source, candidate_source = replacement
        if original_source == candidate_source:
            return None

        relative_path = _repository_relative_path(source_path).as_posix()
        patch = f"diff --git a/{relative_path} b/{relative_path}\n" + "".join(
            difflib.unified_diff(
                original_source.splitlines(keepends=True),
                candidate_source.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )

        fixes_dir = source_path.parent / "_healing_agent_fixes"
        fixes_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        function_name = context.get("function_info", {}).get("name", "unknown")
        patch_path = fixes_dir / f"{timestamp}_{function_name}.patch"
        patch_path.write_text(patch, encoding="utf-8")
        return str(patch_path)
    except Exception as error:
        print(f"♣ Failed to save Git patch: {error}")
        return None
