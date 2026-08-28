"""
Deliver a repair as a pull request, without disturbing the running process.

A healed function keeps the process alive; the repair still has to reach the
repository, or the next deployment silently undoes it. This module turns an
accepted candidate into a branch, a commit and a pull request whose body is the
attempt ledger — what was tried, what verified it, what the model was told.

**Nothing here touches the working tree or the index.** Healing happens inside
a running program, often a scheduled job, and staging a file would be visible
to every other process sharing that checkout: a concurrent `git status`, a
developer's editor, another job. The commit is therefore built with plumbing
against a TEMPORARY index (`GIT_INDEX_FILE`), swapping one blob into HEAD's
tree. The checkout is never read from, never written to, and never locked.

The consequence is deliberate: the pull request contains exactly the repair,
never whatever else happened to be uncommitted on that machine.

Guardrails, none of them optional:

- the branch is always new and prefixed; the default branch is never pushed to;
- pull requests are drafts unless the operator says otherwise;
- the token comes from the environment variable the config NAMES, or from
  `gh` CLI auth — never from the config file;
- failure to deliver is reported and swallowed. A repair that worked must not
  be undone by a network problem.
"""

import os
import subprocess
import tempfile
from typing import Any, Dict, Optional

from .console import emit

GITHUB_API = "https://api.github.com"
DEFAULT_BRANCH_PREFIX = "healing-agent/"


def _git(args, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Run a git command, returning stripped stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=cwd,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip()


def repo_root(path: str) -> Optional[str]:
    """Return the repository root containing ``path``."""
    directory = os.path.dirname(os.path.abspath(path)) or None
    return _git(["rev-parse", "--show-toplevel"], cwd=directory)


def default_branch(root: str) -> Optional[str]:
    """The remote's default branch, which must never be pushed to directly."""
    ref = _git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=root)
    if ref:
        return ref.rsplit("/", 1)[-1]
    for candidate in ("main", "master"):
        if _git(["rev-parse", "--verify", f"origin/{candidate}"], cwd=root):
            return candidate
    return None


def commit_one_file(
    root: str,
    relative_path: str,
    content: str,
    message: str,
    branch: str,
) -> Optional[str]:
    """Commit a single file. Thin wrapper over :func:`commit_files`."""
    return commit_files(root, {relative_path: content}, message, branch)


def commit_files(
    root: str,
    contents: Dict[str, str],
    message: str,
    branch: str,
) -> Optional[str]:
    """Create ``branch`` with these files changed, using a temporary index.

    Returns the new commit SHA, or None. HEAD's tree is the base, so the commit
    carries the repair and nothing else that happens to be uncommitted. Healing
    can touch more than one file - a nested repair re-enters the decorator from
    the reloaded module - and a pull request holding half of a repair would not
    even import.
    """
    if not contents:
        return None
    head = _git(["rev-parse", "HEAD"], cwd=root)
    if not head:
        emit("♣ PR delivery skipped: the repository has no commits yet")
        return None

    entries = []
    for relative_path, content in contents.items():
        # Preserve the tracked mode. Forcing 100644 would silently drop the
        # executable bit from a repaired script, which is a behavior change the
        # reviewer would have to notice in the diff to catch.
        tracked = _git(["ls-files", "-s", "--", relative_path], cwd=root)
        mode = tracked.split()[0] if tracked else "100644"

        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8", newline=""
        ) as handle:
            handle.write(content)
            blob_source = handle.name
        try:
            blob = _git(["hash-object", "-w", blob_source], cwd=root)
        finally:
            try:
                os.unlink(blob_source)
            except OSError:
                pass
        if not blob:
            emit("♣ PR delivery skipped: could not write the repaired blob")
            return None
        entries.append(f"{mode},{blob},{relative_path}")

    index_path = os.path.join(tempfile.mkdtemp(prefix="healing-agent-index-"), "index")
    env = {"GIT_INDEX_FILE": index_path}
    try:
        if _git(["read-tree", head], cwd=root, env=env) is None:
            emit("♣ PR delivery skipped: could not read HEAD into a temporary index")
            return None
        if _git(
            ["update-index", "--add", "--cacheinfo"] + entries, cwd=root, env=env
        ) is None:
            emit("♣ PR delivery skipped: could not stage the repair")
            return None
        tree = _git(["write-tree"], cwd=root, env=env)
        if not tree:
            emit("♣ PR delivery skipped: could not write the tree")
            return None
    finally:
        try:
            os.unlink(index_path)
            os.rmdir(os.path.dirname(index_path))
        except OSError:
            pass

    commit = _git(["commit-tree", tree, "-p", head, "-m", message], cwd=root)
    if not commit:
        emit("♣ PR delivery skipped: could not create the commit")
        return None

    # `update-ref` would happily move an existing branch. A branch that already
    # exists means this exact failure was already proposed (the name is the
    # failure fingerprint), so the honest answer is to leave it alone.
    if _git(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=root):
        emit(f"♣ This failure was already proposed on {branch}; leaving it untouched")
        return None

    if _git(["update-ref", f"refs/heads/{branch}", commit], cwd=root) is None:
        emit(f"♣ PR delivery skipped: could not create the branch {branch}")
        return None
    return commit


def push_branch(root: str, branch: str) -> bool:
    """Push the branch to origin. Never force, never to the default branch."""
    return _git(["push", "origin", f"refs/heads/{branch}:refs/heads/{branch}"], cwd=root) is not None


def build_pr_body(context: Dict[str, Any], config: Dict[str, Any]) -> str:
    """Describe the repair the way a reviewer needs to see it.

    The attempt ledger is the point: "a generated fix" is not reviewable, while
    "three candidates, the first two rejected by the declared verify command
    with this output, the third accepted" is.
    """
    from .attempt_ledger import render as render_attempts

    error = context.get("error") or {}
    function_info = context.get("function_info") or {}
    lines = [
        "Healing Agent repaired this function at runtime and is proposing the "
        "change for review.",
        "",
        f"- **Error:** `{error.get('type')}: {error.get('message')}`",
        f"- **Function:** `{function_info.get('qualname') or function_info.get('name')}`",
        f"- **Failing line:** `{error.get('error_line')}`",
        f"- **Detected:** {context.get('timestamp', '')}",
    ]

    hint = context.get("ai_hint")
    if hint:
        lines += ["", "### Analysis", "", str(hint)]

    lines += render_attempts(context.get("attempts"))

    lines += [
        "",
        "---",
        "",
        "This repair was produced from a live failure: the arguments and local "
        "variables that caused it existed only in that process. It has passed "
        "the gates configured on the machine that made it, and is proposed, "
        "not merged.",
    ]
    return "\n".join(lines)


def open_pull_request(
    repo: str, token: str, branch: str, base: str, title: str, body: str, draft: bool
) -> Optional[str]:
    """Open the pull request and return its URL."""
    import requests

    response = requests.post(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "title": title,
            "body": body,
            "head": branch,
            "base": base,
            "draft": draft,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("html_url")


def deliver(
    context: Dict[str, Any],
    config: Dict[str, Any],
    files: Optional[list] = None,
) -> Optional[str]:
    """Turn an accepted repair into a pull request. Never raises.

    A repair that already worked must not be undone by a network problem, so
    every failure here is reported and swallowed: the process keeps the healed
    code, and the operator learns the delivery did not happen.
    """
    from .github_issue import _repo_relative, _resolve_token, detect_repo

    try:
        github_config = config.get("GITHUB") or {}
        mode = str(github_config.get("pull_request", "off")).lower()
        if mode not in {"draft", "ready"}:
            return None

        # Healing knows which files it rewrote; the failure's own file is only
        # the fallback for a caller that does not.
        repaired = [
            path
            for path in (files or [(context.get("error") or {}).get("file")])
            if path and os.path.exists(str(path))
        ]
        if not repaired:
            emit("♣ PR delivery skipped: no repaired file is on disk")
            return None
        file_path = str(repaired[0])

        root = repo_root(file_path)
        if not root:
            emit("♣ PR delivery skipped: the repaired file is not in a git repository")
            return None

        base = github_config.get("pr_base") or default_branch(root)
        if not base:
            emit("♣ PR delivery skipped: could not determine the base branch")
            return None

        prefix = str(github_config.get("pr_branch_prefix") or DEFAULT_BRANCH_PREFIX)
        fingerprint = _fingerprint(context)
        branch = f"{prefix}{fingerprint}"
        if branch == base:
            emit("♣ PR delivery refused: the branch name collides with the base branch")
            return None

        if _git(["ls-remote", "--heads", "origin", branch], cwd=root):
            emit(f"♣ This failure was already proposed on origin/{branch}")
            return None

        contents = {}
        for path in repaired:
            path = str(path)
            # A file from a different repository cannot go into this commit.
            if repo_root(path) != root:
                emit(f"♣ PR delivery skipped {path}: it is outside {root}")
                continue
            with open(path, "r", encoding="utf-8", newline="") as handle:
                contents[os.path.relpath(path, root).replace(os.sep, "/")] = handle.read()
        if not contents:
            return None

        error = context.get("error") or {}
        function_name = (context.get("function_info") or {}).get("name") or "a function"
        title = f"Heal {function_name}: {error.get('type')} in {_repo_relative(file_path)}"

        commit = commit_files(
            root, contents, f"{title}\n\nProposed by Healing Agent.", branch
        )
        if not commit:
            return None

        if not push_branch(root, branch):
            emit(f"♣ PR delivery failed: could not push {branch}")
            return None

        repo = github_config.get("repo") or detect_repo(file_path)
        token = _resolve_token(config)
        if not repo or not token:
            emit(
                f"♣ Branch {branch} pushed, but no repository/token is configured "
                "to open the pull request"
            )
            return None

        url = open_pull_request(
            repo, token, branch, base, title,
            build_pr_body(context, config), draft=(mode == "draft"),
        )
        emit(f"♣ Repair proposed as a pull request: {url}")
        return url

    except Exception as delivery_error:
        emit(f"♣ PR delivery failed: {delivery_error}")
        return None


def _fingerprint(context: Dict[str, Any]) -> str:
    """Reuse the failure fingerprint, so a recurring failure reuses its branch."""
    from .github_issue import build_fingerprint

    try:
        return build_fingerprint(context)
    except Exception:
        return "repair"
