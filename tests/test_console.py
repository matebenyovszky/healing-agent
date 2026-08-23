"""
Console output must never break the supervised application.

Healing Agent decorates its messages with characters (♣, ⚕️, ✧) that a cp1252
console — the Windows default, inherited by any redirected stdout — cannot
encode. A raw print() would raise UnicodeEncodeError from inside the healing
path and replace the application's own exception.
"""

import importlib
import io

import pytest

console = importlib.import_module("healing_agent.console")
healing_module = importlib.import_module("healing_agent.healing_agent")


class _NarrowStdout(io.StringIO):
    """A stdout that behaves like a cp1252 console."""

    encoding = "cp1252"

    def write(self, text):
        text.encode("cp1252")  # raises UnicodeEncodeError on ♣
        return super().write(text)


def test_emit_degrades_instead_of_raising(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdout", _NarrowStdout())
    console.emit("♣ ⚕️ decorated message with ✧")  # must not raise


def test_emit_supports_the_print_signature(monkeypatch):
    monkeypatch.setattr("sys.stdout", _NarrowStdout())
    console.emit("♣ keys:", ["a", "b"])  # multi-argument form must not raise


def test_emit_writes_normally_when_the_encoding_allows(capsys):
    console.emit("♣ plain")
    assert "♣ plain" in capsys.readouterr().out


def test_emit_survives_a_completely_broken_stdout(monkeypatch):
    class Broken(io.StringIO):
        encoding = "cp1252"

        def write(self, text):
            raise OSError("stream closed")

    monkeypatch.setattr("sys.stdout", Broken())
    console.emit("♣ anything")  # still must not raise


def test_output_failure_never_replaces_the_application_error(monkeypatch):
    """The regression this module exists for: a healing session whose console
    cannot encode the banner must still propagate the ORIGINAL exception."""
    monkeypatch.setattr("sys.stdout", _NarrowStdout())
    monkeypatch.setattr(
        healing_module,
        "load_config",
        lambda: (
            {
                "MAX_ATTEMPTS": 1,
                "AUTO_FIX": False,
                "AUTO_SYSCHANGE": False,
                "BACKUP_ENABLED": False,
                "SAVE_EXCEPTIONS": False,
                "SAVE_AI_FIXES": False,
                "DEBUG": True,
                "GIT_MODE": "off",
            },
            None,
        ),
    )
    monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "hint ♣")
    monkeypatch.setattr(healing_module, "fix", lambda *_a, **_k: None)

    original = KeyError("monthly_total")

    @healing_module.healing_agent
    def broken():
        raise original

    with pytest.raises(KeyError) as caught:
        broken()

    assert caught.value is original, (
        "an encoding failure in the console replaced the application's error"
    )
