"""Optional, repository-aware Git patch support.

The repair engine does not require Git.  When enabled, this module produces a
normal unified diff plus machine-readable metadata, verifies it with
``git apply --check`` and can apply it only when the original file still has
the expected content.  The text-patch API is intentionally language-neutral:
Python function replacement is one adapter, while PowerShell, JavaScript,
shell, and other text files can provide their own complete candidate source.
"""

from __future__ import annotations

import datetime as _datetime
import difflib
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .code_replacer import build_replacement_source
from .console import emit


class GitPatchError(RuntimeError):
    """Raised when a requested Git operation cannot be completed safely."""


@dataclass(frozen=True)
class GitRepository:
    """A discovered repository root and the Git executable used for it."""

    root: Path
    executable: str = "git"

    @classmethod
    def discover(cls, path: Path | str) -> Optional["GitRepository"]:
        candidate = Path(path).resolve()
        if candidate.is_file():
            candidate = candidate.parent
        try:
            result = subprocess.run(
                ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return cls(Path(result.stdout.strip()).resolve())

    def run(self, *arguments: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.executable, "-C", str(self.root), *arguments],
            capture_output=True,
            text=True,
            check=check,
        )

    def head(self) -> Optional[str]:
        result = self.run("rev-parse", "HEAD")
        return result.stdout.strip() if result.returncode == 0 else None


@dataclass(frozen=True)
class GitPatchArtifact:
    """Paths and provenance for a generated patch."""

    patch_path: Path
    metadata_path: Path
    repository_root: Optional[Path]
    relative_path: str
    original_sha256: str
    candidate_sha256: str
    verified: bool


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _repository_relative_path(source_path: Path, repository: Optional[GitRepository] = None) -> Tuple[Optional[Path], str]:
    """Return a repository root and safe POSIX path for a source file."""
    repo = repository or GitRepository.discover(source_path)
    if repo is not None:
        try:
            relative = source_path.resolve().relative_to(repo.root)
            return repo.root, relative.as_posix()
        except ValueError as error:
            raise GitPatchError("Source file is outside the discovered repository") from error

    # A marker is useful in tests and in an uninitialised checkout.  The
    # resulting patch can still be reviewed and checked by ``git apply``.
    for parent in (source_path.parent, *source_path.parents):
        if (parent / ".git").exists():
            return parent, source_path.resolve().relative_to(parent).as_posix()
    return None, source_path.name


def _safe_relative_path(relative_path: str) -> str:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise GitPatchError(f"Unsafe patch path: {relative_path}")
    return path.as_posix()


def build_text_patch(
    source_path: Path | str,
    original_source: str,
    candidate_source: str,
    *,
    repository: Optional[GitRepository] = None,
) -> Tuple[str, Optional[GitRepository], str]:
    """Build a standard unified diff for any UTF-8 text file."""
    path = Path(source_path).resolve()
    if original_source == candidate_source:
        raise GitPatchError("Candidate source is identical to the original")
    repo_root, relative_path = _repository_relative_path(path, repository)
    relative_path = _safe_relative_path(relative_path)
    patch = f"diff --git a/{relative_path} b/{relative_path}\n" + "".join(
        difflib.unified_diff(
            original_source.splitlines(keepends=True),
            candidate_source.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )
    # A marker-only ``.git`` directory is enough to choose stable patch paths,
    # but it is not enough to claim that Git can apply the patch.
    repo = repository or GitRepository.discover(path)
    return patch, repo, relative_path


def save_text_patch(
    source_path: Path | str,
    original_source: str,
    candidate_source: str,
    *,
    output_dir: Optional[Path | str] = None,
    language: Optional[str] = None,
) -> GitPatchArtifact:
    """Write a patch and provenance sidecar for an arbitrary text script."""
    path = Path(source_path).resolve()
    patch, repository, relative_path = build_text_patch(path, original_source, candidate_source)
    marker_root, _ = _repository_relative_path(path, repository)
    root = repository.root if repository is not None else (marker_root or path.parent)
    destination = Path(output_dir).resolve() if output_dir else root / "_healing_agent_fixes"
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = _datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = path.stem.replace(" ", "_") or "source"
    patch_path = destination / f"{timestamp}_{safe_name}.patch"
    metadata_path = patch_path.with_suffix(".json")
    patch_path.write_text(patch, encoding="utf-8")
    metadata: Dict[str, Any] = {
        "format": "healing-agent-git-patch/v1",
        "created_at": _datetime.datetime.now(_datetime.timezone.utc).isoformat(),
        "source_path": str(path),
        "repository_root": str(repository.root) if repository else None,
        "relative_path": relative_path,
        "original_sha256": _sha256(original_source),
        "candidate_sha256": _sha256(candidate_source),
        "git_head": repository.head() if repository else None,
        "language": language or path.suffix.lstrip(".") or "text",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    verified = verify_git_patch(patch_path, repository=repository, working_directory=root)
    return GitPatchArtifact(
        patch_path=patch_path,
        metadata_path=metadata_path,
        repository_root=repository.root if repository else None,
        relative_path=relative_path,
        original_sha256=metadata["original_sha256"],
        candidate_sha256=metadata["candidate_sha256"],
        verified=verified,
    )


def verify_git_patch(
    patch_path: Path | str,
    *,
    repository: Optional[GitRepository] = None,
    working_directory: Optional[Path | str] = None,
) -> bool:
    """Run ``git apply --check`` without changing the working tree."""
    patch = Path(patch_path).resolve()
    repo = repository or GitRepository.discover(patch.parent)
    if repo is None:
        # ``git apply --check`` can validate a patch in a directory containing
        # a marker-only .git, which is useful before a repository is initialised.
        cwd = Path(working_directory).resolve() if working_directory else patch.parent
        result = subprocess.run(["git", "apply", "--check", str(patch)], cwd=cwd, capture_output=True, text=True, check=False)
    else:
        result = repo.run("apply", "--check", str(patch))
    return result.returncode == 0


def apply_git_patch(
    patch_path: Path | str,
    *,
    repository: Optional[GitRepository] = None,
    stage: bool = False,
) -> bool:
    """Safely apply a generated patch after checking its original hash."""
    patch = Path(patch_path).resolve()
    metadata_path = patch.with_suffix(".json")
    if not metadata_path.exists():
        raise GitPatchError("Patch metadata is missing; refusing to apply an untracked patch")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    repo = repository or (
        GitRepository(Path(metadata["repository_root"]))
        if metadata.get("repository_root")
        else GitRepository.discover(patch.parent)
    )
    if repo is None:
        raise GitPatchError("No Git repository was found for this patch")
    relative_path = _safe_relative_path(metadata["relative_path"])
    target = (repo.root / relative_path).resolve()
    if repo.root not in target.parents and target != repo.root:
        raise GitPatchError("Patch target escapes the repository root")
    if not target.exists():
        raise GitPatchError(f"Patch target does not exist: {target}")
    if _sha256(target.read_text(encoding="utf-8")) != metadata["original_sha256"]:
        raise GitPatchError("Patch base no longer matches the source file; refusing to overwrite changes")
    if not verify_git_patch(patch, repository=repo):
        raise GitPatchError("git apply --check rejected the patch")
    arguments = ["apply"]
    if stage:
        arguments.append("--index")
    arguments.append(str(patch))
    result = repo.run(*arguments)
    if result.returncode != 0:
        raise GitPatchError(result.stderr.strip() or "git apply failed")
    return True


def _candidate_sources(context: Dict[str, Any]) -> Tuple[Path, str, str, Optional[str]]:
    path = Path(context["error"]["file"]).resolve()
    language = context.get("language")
    if "original_source" in context and "candidate_source" in context:
        return path, str(context["original_source"]), str(context["candidate_source"]), language
    replacement = build_replacement_source(context, context["fixed_code"])
    if replacement is None:
        raise GitPatchError("Could not build a candidate source replacement")
    return path, replacement[0], replacement[1], language or "python"


def save_git_patch(context: dict) -> Optional[str]:
    """Backward-compatible wrapper returning only the patch path."""
    try:
        path, original, candidate, language = _candidate_sources(context)
        output_dir = context.get("git_patch_dir")
        artifact = save_text_patch(path, original, candidate, output_dir=output_dir, language=language)
        if not artifact.verified:
            return None
        return str(artifact.patch_path)
    except Exception as error:
        emit(f"♣ Failed to save Git patch: {error}")
        return None
