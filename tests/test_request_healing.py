"""
Healing asked for from a handled error branch.

Not every failure worth repairing arrives as an exception: a loader often
detects the problem itself and handles it in an ``if``. That code must be able
to reach the healing loop, and must reach the SAME loop — no second pipeline.
"""

import importlib
import sys

import pytest

healing_module = importlib.import_module("healing_agent.healing_agent")
request_module = importlib.import_module("healing_agent.request")
fixer = importlib.import_module("healing_agent.ai_code_fixer")


def _config(**overrides):
    config = {
        "MAX_ATTEMPTS": 1,
        "AUTO_FIX": True,
        "AUTO_SYSCHANGE": False,
        "BACKUP_ENABLED": True,
        "RESTORE_ON_FAILURE": True,
        "SAVE_EXCEPTIONS": False,
        "SAVE_AI_FIXES": False,
        "DEBUG": False,
        "GIT_MODE": "off",
    }
    config.update(overrides)
    return config


MODULE_SOURCE = '''
import healing_agent

@healing_agent
def load_sales(rows):
    if "amount" not in rows[0]:
        healing_agent.request_healing(
            "input has no 'amount' column",
            details=sorted(rows[0]),
        )
    return sum(int(row["amount"]) for row in rows)
'''

# The repair the model would write: map the drifted header, keep the old one.
HEALED = '''def load_sales(rows):
    aliases = ("amount", "osszeg")
    key = next((a for a in aliases if a in rows[0]), None)
    if key is None:
        raise KeyError("no amount column")
    return sum(int(row[key]) for row in rows)
'''


def _load(tmp_path, monkeypatch, name, fixed_code=HEALED, **config_overrides):
    path = tmp_path / f"{name}.py"
    path.write_text(MODULE_SOURCE, encoding="utf-8")
    monkeypatch.setattr(
        healing_module, "load_config", lambda: (_config(**config_overrides), None)
    )
    monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "stub hint")
    monkeypatch.setattr(healing_module, "fix", lambda *_a, **_k: fixed_code)

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return path, module


def test_request_healing_raises_so_control_leaves_the_function():
    with pytest.raises(request_module.HealingRequested) as caught:
        request_module.request_healing("bad shape", details={"headers": ["a"]})
    assert caught.value.reason == "bad shape"
    assert caught.value.details == {"headers": ["a"]}
    assert "bad shape" in str(caught.value)


def test_a_handled_branch_triggers_the_normal_healing_loop(tmp_path, monkeypatch):
    """The whole point: no second pipeline. The same loop repairs, applies and
    re-runs, and the caller gets the repaired result."""
    path, module = _load(tmp_path, monkeypatch, "request_demo_ok")

    result = module.load_sales([{"osszeg": "1200"}, {"osszeg": "800"}])

    assert result == 2000
    healed_source = path.read_text(encoding="utf-8")
    assert "aliases" in healed_source, "the repair was not applied to the file"


def test_the_old_format_still_works_after_the_requested_repair(tmp_path, monkeypatch):
    path, module = _load(tmp_path, monkeypatch, "request_demo_both")
    module.load_sales([{"osszeg": "1200"}])

    reloaded = importlib.util.spec_from_file_location("request_demo_both_v2", path)
    healed = importlib.util.module_from_spec(reloaded)
    sys.modules["request_demo_both_v2"] = healed
    reloaded.loader.exec_module(healed)

    assert healed.load_sales([{"amount": "1200"}, {"amount": "800"}]) == 2000
    assert healed.load_sales([{"osszeg": "1200"}, {"osszeg": "800"}]) == 2000


def test_an_unanswered_request_propagates_rather_than_returning_none(
    tmp_path, monkeypatch
):
    """A program that asked a question deserves to hear it went unanswered."""
    path, module = _load(
        tmp_path, monkeypatch, "request_demo_failed", fixed_code=None
    )
    before = path.read_bytes()

    with pytest.raises(request_module.HealingRequested):
        module.load_sales([{"osszeg": "1200"}])

    assert path.read_bytes() == before, "the source changed despite no repair"


def test_the_prompt_states_that_the_program_asked_and_why():
    context = {
        "function_info": {"name": "load_sales", "source_code": "def load_sales(): ...",
                          "signature": "()", "module": "demo"},
        "function_arguments": {},
        "error": {"type": "HealingRequested", "message": "healing requested: no amount",
                  "line_number": 3, "error_line": "request_healing(...)",
                  "exception_attrs": {}, "traceback_frames": [], "traceback": "",
                  "function_name": "load_sales"},
        "healing_request": {"reason": "input has no 'amount' column",
                            "details": ["datum", "osszeg", "ugyfel"]},
    }
    prompt = fixer.prepare_fix_prompt(context)

    assert "did not crash" in prompt
    assert "input has no 'amount' column" in prompt
    assert "osszeg" in prompt, "supporting details were not passed to the model"
    # And an ordinary exception must not gain that framing.
    del context["healing_request"]
    assert "did not crash" not in fixer.prepare_fix_prompt(context)
