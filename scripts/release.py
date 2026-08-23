"""Release Healing Agent.

Everything a release needs, in one command. The checks exist because each of
them has a failure mode that is expensive AFTER publishing: a PyPI version can
never be reused, so a wrong number, a dirty tree or a red test suite has to be
caught here rather than fixed later.

    python scripts/release.py            # preflight only: verify and build
    python scripts/release.py --publish  # preflight, then tag and push

The push of a ``vX.Y.Z`` tag is what publishes: the *Publish Python Package*
workflow builds from that commit and uploads to PyPI with Trusted Publishing
(short-lived OIDC credentials, no API token anywhere). This script never
uploads anything itself.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"[ ok ] {message}")


def run(*command: str, capture: bool = False) -> str:
    """Run a command in the repository root, failing the release on error."""
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=capture,
    )
    if result.returncode != 0:
        if capture and result.stdout:
            print(result.stdout)
        if capture and result.stderr:
            print(result.stderr)
        fail(f"command failed: {' '.join(command)}")
    return (result.stdout or "").strip() if capture else ""


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        fail("pyproject.toml has no [project] version")
    return match.group(1)


def check_git_state(version: str) -> None:
    if run("git", "status", "--porcelain", capture=True):
        fail("working tree is not clean; commit or stash first")
    ok("working tree is clean")

    branch = run("git", "rev-parse", "--abbrev-ref", "HEAD", capture=True)
    if branch != "main":
        fail(f"releases are cut from main, not {branch}")

    run("git", "fetch", "--tags", "--quiet", capture=True)
    local = run("git", "rev-parse", "HEAD", capture=True)
    remote = run("git", "rev-parse", "origin/main", capture=True)
    if local != remote:
        fail("main and origin/main differ; push or pull before releasing")
    ok("main matches origin/main")

    tag = f"v{version}"
    existing = run("git", "tag", "--list", tag, capture=True)
    if existing:
        fail(f"{tag} already exists — a published version is never reused")
    ok(f"{tag} is unused")


def check_changelog(version: str) -> None:
    """The changelog must carry a DATED section for this version.

    An `[Unreleased]` heading left in place is the most common release mistake
    and the one nobody notices until the PyPI page is live.
    """
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}", text, re.MULTILINE):
        fail(
            f"CHANGELOG.md has no dated '## [{version}] - YYYY-MM-DD' section "
            "(is it still marked Unreleased?)"
        )
    ok(f"CHANGELOG.md documents {version}")


def check_schema_version(version: str) -> None:
    """Config schema marker must not claim a version that does not exist yet.

    tests/test_version.py enforces this too; checking here gives the actionable
    message instead of a test failure three steps later.
    """
    sys.path.insert(0, str(ROOT))
    from healing_agent._version import CONFIG_SCHEMA_VERSION, parse_version

    if parse_version(CONFIG_SCHEMA_VERSION) > parse_version(version):
        fail(
            f"CONFIG_SCHEMA_VERSION ({CONFIG_SCHEMA_VERSION}) is ahead of the "
            f"release version ({version})"
        )
    ok(f"config schema marker {CONFIG_SCHEMA_VERSION} is consistent")


def build(version: str) -> None:
    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    run(sys.executable, "-m", "build")
    artifacts = sorted(p.name for p in dist.glob("*"))
    expected = {
        f"healing_agent-{version}-py3-none-any.whl",
        f"healing_agent-{version}.tar.gz",
    }
    missing = expected - set(artifacts)
    if missing:
        fail(f"build produced {artifacts}, missing {sorted(missing)}")
    run(sys.executable, "-m", "twine", "check", *[str(dist / name) for name in artifacts])
    ok(f"built and validated {', '.join(artifacts)}")


def publish(version: str) -> None:
    tag = f"v{version}"
    run("git", "tag", "-a", tag, "-m", f"healing-agent {version}")
    run("git", "push", "origin", tag)
    ok(f"pushed {tag} — the Publish workflow now builds and uploads to PyPI")
    print(
        "\nWatch it:  gh run watch --repo matebenyovszky/healing-agent\n"
        f"Then:      gh release create {tag} --notes-from-changelog (or via the web UI)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="after a green preflight, tag the release and push it (this publishes)",
    )
    args = parser.parse_args()

    version = project_version()
    print(f"\nReleasing healing-agent {version}\n")

    check_git_state(version)
    check_changelog(version)
    check_schema_version(version)
    run(sys.executable, "-m", "ruff", "check", ".")
    ok("ruff check passed")
    run(sys.executable, "-m", "pytest", "-q")
    ok("test suite passed")
    build(version)

    if not args.publish:
        print(f"\nPreflight green. Publish with:  python scripts/release.py --publish\n")
        return
    publish(version)


if __name__ == "__main__":
    main()
