import subprocess

import pytest

from scripts import test_runner


def test_runner_uses_pytest_discovery_and_propagates_failure(monkeypatch):
    captured = {}

    def fail(command, cwd, check):
        captured.update(command=command, cwd=cwd, check=check)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(test_runner.subprocess, "run", fail)

    with pytest.raises(subprocess.CalledProcessError):
        test_runner.execute_tests(["-q"])

    assert captured["command"][:3] == [
        test_runner.sys.executable,
        "-m",
        "pytest",
    ]
    assert captured["command"][-1] == "-q"
    assert captured["check"] is True
