"""The PR flow runs inside a live process, so its guarantees are mostly about
what it does NOT do: touch the working tree, touch the index, move an existing
branch, target the default branch, or let a delivery failure undo a working
repair. These are tested against a real git repository - plumbing behavior is
exactly what a mock would get wrong - with only the network calls replaced.
"""

import importlib
import subprocess

import pytest

pr_delivery = importlib.import_module("healing_agent.pr_delivery")
config_loader = importlib.import_module("healing_agent.config_loader")


def git(repo, *args):
    result = subprocess.run(
        ["git"] + list(args), cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A real repository with one commit, a staged change and a dirty file."""
    root = tmp_path / "app"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "loader.py").write_text("def load():\n    return 1\n", encoding="utf-8")
    (root / "other.py").write_text("ORIGINAL = 1\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "initial")

    # State that must survive untouched, and must NOT reach the commit.
    (root / "staged.py").write_text("STAGED = True\n", encoding="utf-8")
    git(root, "add", "staged.py")
    (root / "other.py").write_text("ORIGINAL = 2\n", encoding="utf-8")
    return root


def context_for(repo):
    return {
        "error": {
            "type": "KeyError",
            "message": "'amount'",
            "file": str(repo / "loader.py"),
            "error_line": "return row['amount']",
        },
        "function_info": {"name": "load", "qualname": "load"},
        "timestamp": "2026-08-28T10:00:00",
        "ai_hint": "The column was renamed.",
        "attempts": [
            {
                "attempt": 1,
                "outcome": "rejected_by_gate",
                "summary": "rejected by a verify gate",
                "detail": "exit code 1",
            },
            {"attempt": 2, "outcome": "healed", "summary": "accepted and applied"},
        ],
    }


def test_commit_leaves_the_working_tree_and_index_exactly_as_they_were(repo):
    before = git(repo, "status", "--porcelain")
    head_before = git(repo, "rev-parse", "HEAD")

    commit = pr_delivery.commit_one_file(
        str(repo), "loader.py", "def load():\n    return 2\n", "repair", "healing/x"
    )

    assert commit
    assert git(repo, "status", "--porcelain") == before
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    # The file on disk is whatever the healing process wrote there; committing
    # did not rewrite it.
    assert (repo / "loader.py").read_text(encoding="utf-8") == "def load():\n    return 1\n"


def test_commit_carries_the_repair_and_nothing_else_uncommitted(repo):
    commit = pr_delivery.commit_one_file(
        str(repo), "loader.py", "def load():\n    return 2\n", "repair", "healing/x"
    )

    assert git(repo, "show", f"{commit}:loader.py") == "def load():\n    return 2"
    # The dirty edit and the staged file were never part of this repair.
    assert git(repo, "show", f"{commit}:other.py") == "ORIGINAL = 1"
    with pytest.raises(subprocess.CalledProcessError):
        git(repo, "show", f"{commit}:staged.py")


def test_commit_preserves_the_executable_bit(repo):
    git(repo, "update-index", "--chmod=+x", "loader.py")
    git(repo, "commit", "-m", "make executable")

    commit = pr_delivery.commit_one_file(
        str(repo), "loader.py", "def load():\n    return 2\n", "repair", "healing/x"
    )

    assert git(repo, "ls-tree", commit, "loader.py").startswith("100755")


def test_an_existing_branch_is_never_moved(repo):
    first = pr_delivery.commit_one_file(
        str(repo), "loader.py", "def load():\n    return 2\n", "repair", "healing/x"
    )
    second = pr_delivery.commit_one_file(
        str(repo), "loader.py", "def load():\n    return 3\n", "repair", "healing/x"
    )

    assert second is None
    assert git(repo, "rev-parse", "refs/heads/healing/x") == first


def test_delivery_is_off_by_default(repo):
    assert pr_delivery.deliver(context_for(repo), {}) is None
    assert pr_delivery.deliver(context_for(repo), {"GITHUB": {}}) is None


def test_a_successful_delivery_opens_a_draft_pull_request(repo, monkeypatch):
    (repo / "loader.py").write_text("def load():\n    return 2\n", encoding="utf-8")
    pushed = []
    opened = {}

    def fake_push(root, branch):
        pushed.append(branch)
        return True

    def fake_open(repository, token, branch, base, title, body, draft):
        opened.update(
            repository=repository, token=token, branch=branch, base=base,
            title=title, body=body, draft=draft,
        )
        return "https://github.com/o/n/pull/7"

    monkeypatch.setattr(pr_delivery, "push_branch", fake_push)
    monkeypatch.setattr(pr_delivery, "default_branch", lambda root: "main")
    monkeypatch.setattr(pr_delivery, "open_pull_request", fake_open)
    monkeypatch.setenv("GH_TEST_TOKEN", "t0ken")

    url = pr_delivery.deliver(
        context_for(repo),
        {"GITHUB": {"pull_request": "draft", "repo": "o/n", "token_env": "GH_TEST_TOKEN"}},
    )

    assert url == "https://github.com/o/n/pull/7"
    assert pushed and pushed[0].startswith("healing-agent/")
    assert opened["draft"] is True
    assert opened["base"] == "main"
    assert opened["repository"] == "o/n"
    # The reviewer must see what was tried, not only the final diff.
    assert "rejected by a verify gate" in opened["body"]
    assert "The column was renamed." in opened["body"]
    assert git(repo, "show", f"{pushed[0]}:loader.py") == "def load():\n    return 2"


def test_ready_mode_opens_a_pull_request_that_is_not_a_draft(repo, monkeypatch):
    opened = {}
    monkeypatch.setattr(pr_delivery, "push_branch", lambda root, branch: True)
    monkeypatch.setattr(pr_delivery, "default_branch", lambda root: "main")
    monkeypatch.setattr(
        pr_delivery,
        "open_pull_request",
        lambda *args, **kwargs: opened.update(kwargs) or "https://example.invalid/pr/1",
    )
    monkeypatch.setenv("GH_TEST_TOKEN", "t0ken")

    pr_delivery.deliver(
        context_for(repo),
        {"GITHUB": {"pull_request": "ready", "repo": "o/n", "token_env": "GH_TEST_TOKEN"}},
    )

    assert opened["draft"] is False


def test_a_failed_push_never_reaches_the_api(repo, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("must not open a pull request for an unpushed branch")

    monkeypatch.setattr(pr_delivery, "push_branch", lambda root, branch: False)
    monkeypatch.setattr(pr_delivery, "default_branch", lambda root: "main")
    monkeypatch.setattr(pr_delivery, "open_pull_request", explode)

    assert pr_delivery.deliver(
        context_for(repo), {"GITHUB": {"pull_request": "draft", "repo": "o/n"}}
    ) is None


def test_an_exploding_api_never_propagates(repo, monkeypatch):
    """A repair that already worked must not be undone by a network problem."""
    def explode(*args, **kwargs):
        raise RuntimeError("422 a pull request already exists")

    monkeypatch.setattr(pr_delivery, "push_branch", lambda root, branch: True)
    monkeypatch.setattr(pr_delivery, "default_branch", lambda root: "main")
    monkeypatch.setattr(pr_delivery, "open_pull_request", explode)
    monkeypatch.setenv("GH_TEST_TOKEN", "t0ken")

    assert pr_delivery.deliver(
        context_for(repo),
        {"GITHUB": {"pull_request": "draft", "repo": "o/n", "token_env": "GH_TEST_TOKEN"}},
    ) is None


def test_the_base_branch_is_never_the_push_target(repo, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("must not push when the branch collides with the base")

    monkeypatch.setattr(pr_delivery, "default_branch", lambda root: "main")
    monkeypatch.setattr(pr_delivery, "push_branch", explode)
    monkeypatch.setattr(pr_delivery, "_fingerprint", lambda context: "main")

    assert pr_delivery.deliver(
        context_for(repo),
        {"GITHUB": {"pull_request": "draft", "repo": "o/n", "pr_branch_prefix": ""}},
    ) is None


def test_a_file_outside_a_repository_is_skipped(repo, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("must not commit outside a repository")

    monkeypatch.setattr(pr_delivery, "repo_root", lambda path: None)
    monkeypatch.setattr(pr_delivery, "commit_one_file", explode)

    assert pr_delivery.deliver(
        context_for(repo), {"GITHUB": {"pull_request": "draft"}}
    ) is None


def test_a_vanished_file_is_skipped(repo, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("must not commit a file that is not on disk")

    monkeypatch.setattr(pr_delivery, "commit_one_file", explode)
    context = context_for(repo)
    context["error"]["file"] = str(repo / "gone.py")

    assert pr_delivery.deliver(context, {"GITHUB": {"pull_request": "draft"}}) is None


def test_an_unknown_mode_is_rejected_by_config_validation():
    config = config_loader.load_template_defaults()
    config["AI_PROVIDER"] = "openai"
    config["OPENAI"] = {"api_key": "sk-not-a-real-key"}
    config["GITHUB"] = dict(config["GITHUB"], pull_request="yes-please")

    with pytest.raises(ValueError, match="pull_request"):
        config_loader.validate_config(config)


def remote_clone(tmp_path):
    """A clone with an `origin` bare remote, one commit, and a repaired file."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    clone = tmp_path / "clone"
    git(tmp_path, "clone", str(origin), str(clone))
    git(clone, "config", "user.email", "test@example.com")
    git(clone, "config", "user.name", "Test")
    (clone / "loader.py").write_text("def load():\n    return 1\n", encoding="utf-8")
    git(clone, "add", ".")
    git(clone, "commit", "-m", "initial")
    git(clone, "push", "origin", "main")
    # What the healing process left on disk after repairing the function.
    (clone / "loader.py").write_text("def load():\n    return 2\n", encoding="utf-8")
    return origin, clone


def test_the_branch_really_reaches_the_remote(tmp_path, monkeypatch):
    """The push refspec is exercised for real against a bare remote.

    Mocking the push would leave the one command that talks to a remote
    untested, and a wrong refspec fails only in production.
    """
    origin, clone = remote_clone(tmp_path)
    opened = {}
    monkeypatch.setattr(
        pr_delivery,
        "open_pull_request",
        lambda *args, **kwargs: opened.update(branch=args[2], base=args[3]) or "https://x/pr/1",
    )
    monkeypatch.setenv("GH_TEST_TOKEN", "t0ken")

    url = pr_delivery.deliver(
        context_for(clone),
        {"GITHUB": {"pull_request": "draft", "repo": "o/n", "token_env": "GH_TEST_TOKEN"}},
    )

    assert url == "https://x/pr/1"
    assert opened["base"] == "main"
    assert git(origin, "show", f"{opened['branch']}:loader.py") == "def load():\n    return 2"
    # The remote's default branch is untouched by the delivery.
    assert git(origin, "show", "main:loader.py") == "def load():\n    return 1"


def test_the_same_failure_is_never_proposed_twice(tmp_path, monkeypatch):
    origin, clone = remote_clone(tmp_path)
    calls = []
    monkeypatch.setattr(
        pr_delivery,
        "open_pull_request",
        lambda *args, **kwargs: calls.append(args[2]) or "https://x/pr/1",
    )
    monkeypatch.setenv("GH_TEST_TOKEN", "t0ken")
    config = {
        "GITHUB": {"pull_request": "draft", "repo": "o/n", "token_env": "GH_TEST_TOKEN"}
    }

    assert pr_delivery.deliver(context_for(clone), config) == "https://x/pr/1"
    # The branch name IS the failure fingerprint, so a recurrence - in another
    # process, or after a restart - must not open a second pull request.
    assert pr_delivery.deliver(context_for(clone), config) is None
    assert len(calls) == 1


# --- end to end: a real heal in a real repository ---------------------------
# The delivery hook lives in the outermost session's teardown, which is also
# where escalation lives. Nesting is what makes that placement matter, so it is
# exercised through an actual repair rather than by calling deliver() directly.

healing_module = importlib.import_module("healing_agent.healing_agent")


def heal_config(max_attempts=1, **github):
    return {
        "MAX_ATTEMPTS": max_attempts,
        "AUTO_FIX": True,
        "AUTO_SYSCHANGE": False,
        "BACKUP_ENABLED": False,
        "SAVE_EXCEPTIONS": False,
        "SAVE_AI_FIXES": False,
        "DEBUG": False,
        "GITHUB": {
            "pull_request": "draft",
            "repo": "o/n",
            "token_env": "GH_TEST_TOKEN",
            **github,
        },
    }


def run_healed_module(repo, source, monkeypatch, name):
    """Import a module from ``repo`` and call its decorated function."""
    import importlib.util
    import sys

    path = repo / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    git(repo, "add", f"{name}.py")
    git(repo, "commit", "-m", f"add {name}")

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    try:
        return module.pick({})
    finally:
        sys.modules.pop(name, None)


@pytest.fixture
def delivery_spy(monkeypatch):
    """Capture what the delivery would have sent, without a network."""
    opened = []
    monkeypatch.setattr(pr_delivery, "push_branch", lambda root, branch: True)
    monkeypatch.setattr(pr_delivery, "default_branch", lambda root: "main")
    monkeypatch.setattr(
        pr_delivery,
        "open_pull_request",
        lambda repository, token, branch, base, title, body, draft: opened.append(
            {"branch": branch, "title": title, "body": body, "draft": draft}
        )
        or f"https://x/pr/{len(opened)}",
    )
    monkeypatch.setenv("GH_TEST_TOKEN", "t0ken")
    return opened


def test_a_successful_heal_proposes_the_repair(repo, monkeypatch, delivery_spy):
    monkeypatch.setattr(healing_module, "load_config", lambda: (heal_config(), None))
    monkeypatch.setattr(healing_module, "generate_hint", lambda *a, **k: "The key is absent.")
    monkeypatch.setattr(
        healing_module, "fix", lambda *a, **k: 'def pick(v):\n    return "healed"\n'
    )

    result = run_healed_module(
        repo,
        "import healing_agent\n\n@healing_agent\ndef pick(v):\n    return v['amount']\n",
        monkeypatch,
        "one_shot",
    )

    assert result == "healed"
    assert len(delivery_spy) == 1
    proposal = delivery_spy[0]
    assert proposal["draft"] is True
    assert "KeyError" in proposal["title"]
    assert git(repo, "show", f"{proposal['branch']}:one_shot.py").endswith('return "healed"')


def test_nesting_proposes_the_original_failure_exactly_once(repo, monkeypatch, delivery_spy):
    """A nested repair must not produce a second pull request.

    Each nested attempt captures its own context, describing the error of the
    candidate that failed. Delivering from there would open one pull request
    per attempt, and title them after Healing Agent's own dead ends instead of
    the failure the application actually hit.
    """
    candidates = iter(
        [
            'def pick(v):\n    return v["still_missing"]\n',
            'def pick(v):\n    return "healed at last"\n',
        ]
    )
    monkeypatch.setattr(healing_module, "load_config", lambda: (heal_config(max_attempts=3), None))
    monkeypatch.setattr(healing_module, "generate_hint", lambda *a, **k: "hint")
    monkeypatch.setattr(healing_module, "fix", lambda *a, **k: next(candidates))

    result = run_healed_module(
        repo,
        "import healing_agent\n\n@healing_agent\ndef pick(v):\n    return v['amount']\n",
        monkeypatch,
        "nested",
    )

    assert result == "healed at last"
    assert len(delivery_spy) == 1, "one repair, one pull request"
    body = delivery_spy[0]["body"]
    assert "'amount'" in body, "the pull request describes the ORIGINAL failure"
    assert "still_missing" not in delivery_spy[0]["title"]
    # And the reviewer sees the dead end, because that is what makes the
    # accepted candidate trustworthy.
    assert "Attempt 1" in body and "Attempt 2" in body


def test_a_failed_heal_proposes_nothing(repo, monkeypatch, delivery_spy):
    monkeypatch.setattr(healing_module, "load_config", lambda: (heal_config(), None))
    monkeypatch.setattr(healing_module, "generate_hint", lambda *a, **k: "hint")
    monkeypatch.setattr(
        healing_module, "fix", lambda *a, **k: 'def pick(v):\n    return v["nope"]\n'
    )

    with pytest.raises(KeyError):
        run_healed_module(
            repo,
            "import healing_agent\n\n@healing_agent\ndef pick(v):\n    return v['amount']\n",
            monkeypatch,
            "never_healed",
        )

    assert delivery_spy == [], "a failure escalates as an issue, it does not propose a fix"
