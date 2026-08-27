"""
GitHub issue escalation for failures healing could not repair.

When automatic healing gives up, the attempt should not be lost: an issue in
the application's own repository turns it into work an agent or a human can
pick up, answering with a pull request.

Privacy is explicit policy. Exception context and captured variables may hold
sensitive data, so the amount of detail that leaves the machine is chosen with
`GITHUB["issue_detail"]`:

    reference       only error/function identity plus pointers to the LOCAL
                    artifacts (default; no captured values are uploaded)
    redacted        additionally attach the redacted context JSON
    ai-anonymized   additionally attach an AI-anonymized context JSON

Authentication is host-level: the config names the environment variable that
holds the token (never the token itself), and the `gh` CLI is used as a
fallback. Nothing here may ever raise into the healed application.
"""

import logging
import datetime
import hashlib
import json
import os
import re
import subprocess
from typing import Any, Dict, Optional
from .console import emit

GITHUB_API = "https://api.github.com"
FINGERPRINT_MARKER = "healing-agent-fingerprint:"
DEFAULT_LABEL = "healing-agent"
# GitHub rejects bodies over 65536 characters; keep a wide safety margin.
MAX_ATTACHMENT_CHARS = 30000


def _run(argv, cwd: Optional[str] = None) -> Optional[str]:
    """Run a command and return stripped stdout, or None on any failure."""
    try:
        result = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=30, check=False
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


def detect_repo(file_path: str) -> Optional[str]:
    """Return "owner/name" for the git remote containing file_path."""
    directory = os.path.dirname(os.path.abspath(file_path)) or None
    url = _run(["git", "remote", "get-url", "origin"], cwd=directory)
    if not url:
        return None
    match = re.search(r"github\.com[:/]+([^/]+)/(.+?)(?:\.git)?/?$", url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def _repo_relative(file_path: str) -> str:
    """Prefer a repository-relative path so local usernames are not exposed."""
    directory = os.path.dirname(os.path.abspath(file_path)) or None
    root = _run(["git", "rev-parse", "--show-toplevel"], cwd=directory)
    if root:
        try:
            return os.path.relpath(file_path, root).replace(os.sep, "/")
        except Exception:
            pass
    return os.path.basename(file_path)


_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def normalize_message(message: str) -> str:
    """Collapse varying numbers so repeated failures share one fingerprint.

    Digit runs outside quotes are replaced ("row 5 failed" and "row 812
    failed" become the same failure), while quoted identifiers are preserved
    verbatim: `KeyError: 'amount'` and `KeyError: 'osszeg'` are two different
    drifted columns and deserve two issues.
    """
    result = []
    position = 0
    for quoted in _QUOTED.finditer(message):
        result.append(re.sub(r"\d+", "N", message[position : quoted.start()]))
        result.append(quoted.group(0))
        position = quoted.end()
    result.append(re.sub(r"\d+", "N", message[position:]))
    return "".join(result)[:500]


def build_fingerprint(context: Dict[str, Any]) -> str:
    """Stable identity of a failure, used to avoid duplicate issues.

    Deliberately uses the failing line's TEXT rather than its number: line
    numbers shift on every edit and would fragment one failure into many
    issues.
    """
    error = context.get("error") or {}
    function_info = context.get("function_info") or {}
    parts = [
        str(error.get("type")),
        str(function_info.get("qualname") or function_info.get("name")),
        _repo_relative(str(error.get("file") or "")),
        str(error.get("error_line") or "").strip(),
        normalize_message(str(error.get("message") or "")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _anonymize(payload: str, config: Dict[str, Any]) -> Optional[str]:
    """Ask the configured model to replace concrete values with placeholders."""
    from .ai_broker import get_ai_response

    prompt = (
        "The following JSON is a program failure report that may contain "
        "personal or business data. Replace every concrete data VALUE "
        "(names, identifiers, amounts, addresses, file contents) with a "
        "generic placeholder such as <name>, <id> or <amount>, while keeping "
        "the JSON structure, keys, types and error semantics intact. "
        "Return only the resulting JSON.\n\n" + payload
    )
    try:
        response = get_ai_response(prompt, config, system_role="report")
    except Exception as error:
        emit(f"♣ Issue anonymization failed, omitting the attachment: {error}")
        return None

    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*|\s*```$", "", response.strip())
    try:
        json.loads(cleaned)
    except Exception:
        emit("♣ Issue anonymization did not return valid JSON, omitting it")
        return None
    return cleaned


def build_issue(context: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, str]:
    """Build the issue title and body for a failed healing session."""
    github_config = config.get("GITHUB") or {}
    detail = str(github_config.get("issue_detail", "redacted")).lower()

    error = context.get("error") or {}
    function_info = context.get("function_info") or {}
    function_name = function_info.get("name") or error.get("function_name") or "unknown"
    file_path = str(error.get("file") or "")
    relative_path = _repo_relative(file_path) if file_path else "unknown"
    fingerprint = build_fingerprint(context)

    title = (
        f"[healing-agent] {error.get('type', 'Failure')} in {function_name} "
        f"({relative_path})"
    )

    lines = [
        (
            "Automatic healing did not produce a working repair, so this "
            "failure is escalated for review."
        ),
        "",
        f"- **Error:** `{error.get('type')}: {error.get('message')}`",
        f"- **Function:** `{function_name}`",
        f"- **Location:** `{relative_path}:{error.get('line_number')}`",
        f"- **Failing line:** `{error.get('error_line')}`",
        f"- **Detected:** {context.get('timestamp', datetime.datetime.now().isoformat())}",
        f"- **Detail level:** `{detail}`",
        "",
        (
            "The full exception context, captured variables and the generated "
            "candidate fixes stay on the machine that ran the job:"
        ),
        "",
        "- exception context: `_healing_agent_exceptions/`",
        "- generated candidates: `_healing_agent_fixes/`",
        "- pre-healing source backup: `_healing_agent_backups/`",
    ]

    hint = context.get("ai_hint")
    if hint:
        lines += ["", "### Analysis", "", str(hint)]

    if detail in {"redacted", "ai-anonymized"}:
        # Trim on the way out: the artifact on disk stays rich, the issue body
        # has a hard GitHub limit and a human has to read it.
        from .evidence import select

        payload = json.dumps(
            select(context, config, "issue"), indent=2, ensure_ascii=False, default=str
        )
        if detail == "ai-anonymized":
            payload = _anonymize(payload, config)
        if payload:
            if len(payload) > MAX_ATTACHMENT_CHARS:
                payload = payload[:MAX_ATTACHMENT_CHARS] + "\n… truncated …"
            label = (
                "Redacted context"
                if detail == "redacted"
                else "AI-anonymized context"
            )
            lines += [
                "",
                f"### {label}",
                "",
                "<details><summary>Show context</summary>",
                "",
                "```json",
                payload,
                "```",
                "",
                "</details>",
            ]

    lines += ["", f"<!-- {FINGERPRINT_MARKER} {fingerprint} -->"]
    return {"title": title, "body": "\n".join(lines), "fingerprint": fingerprint}


def _resolve_token(config: Dict[str, Any]) -> Optional[str]:
    """Read the token from the configured environment variable, or gh CLI."""
    github_config = config.get("GITHUB") or {}
    env_name = github_config.get("token_env") or "GITHUB_TOKEN"
    token = os.getenv(str(env_name))
    if token:
        return token
    return _run(["gh", "auth", "token"])


def find_existing_issue(
    repo: str, token: str, fingerprint: str, label: str
) -> Optional[str]:
    """Return the URL of an open issue for the same failure, if any.

    Open issues are listed rather than queried through the search API, whose
    indexing lag would let duplicates slip through for repeated failures.
    """
    import requests

    try:
        response = requests.get(
            f"{GITHUB_API}/repos/{repo}/issues",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            params={"state": "open", "labels": label, "per_page": 100},
            timeout=30,
        )
        response.raise_for_status()
        for issue in response.json():
            if fingerprint in (issue.get("body") or ""):
                return issue.get("html_url")
    except Exception as error:
        emit(f"♣ Could not check for an existing issue: {error}", level=logging.ERROR)
    return None


def open_issue_for_failure(
    context: Dict[str, Any], config: Dict[str, Any]
) -> Optional[str]:
    """Escalate a failed healing session as a GitHub issue.

    Returns the issue URL, the URL of the existing duplicate, or None. Never
    raises: an escalation problem must not replace the application's error.
    """
    import requests

    try:
        github_config = config.get("GITHUB") or {}
        if not github_config.get("issue_on_failure", False):
            return None

        repo = github_config.get("repo") or detect_repo(
            str((context.get("error") or {}).get("file") or "")
        )
        if not repo:
            emit("♣ Issue escalation skipped: no GitHub repository configured/detected")
            return None

        token = _resolve_token(config)
        if not token:
            env_name = github_config.get("token_env") or "GITHUB_TOKEN"
            emit(
                f"♣ Issue escalation skipped: no token in ${env_name} and no gh CLI login"
            )
            return None

        label = str(github_config.get("issue_label") or DEFAULT_LABEL)
        issue = build_issue(context, config)

        existing = find_existing_issue(repo, token, issue["fingerprint"], label)
        if existing:
            emit(f"♣ Failure already tracked, no duplicate opened: {existing}")
            return existing

        response = requests.post(
            f"{GITHUB_API}/repos/{repo}/issues",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "title": issue["title"],
                "body": issue["body"],
                "labels": [label],
            },
            timeout=30,
        )
        response.raise_for_status()
        url = response.json().get("html_url")
        emit(f"♣ Failure escalated to GitHub issue: {url}")
        return url

    except Exception as error:
        emit(f"♣ Issue escalation failed: {error}")
        return None
