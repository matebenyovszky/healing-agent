import importlib


ai_code_fixer = importlib.import_module("healing_agent.ai_code_fixer")


def _context():
    return {
        "function_info": {
            "name": "divide_numbers",
            "signature": "divide_numbers(a, b)",
            "module": "test_module",
            "source_code": "def divide_numbers(a, b):\n    return a / b",
        },
        "function_arguments": {
            "a": {"value": 10, "type": "int"},
            "b": {"value": 0, "type": "int"},
        },
        "error": {
            "type": "ZeroDivisionError",
            "message": "division by zero",
            "line_number": 2,
            "error_line": "return a / b",
            "exception_attrs": {},
            "traceback_frames": [],
        },
    }


def test_fix_strips_markdown_and_adds_decorator(monkeypatch):
    monkeypatch.setattr(
        ai_code_fixer,
        "get_ai_response",
        lambda *_args, **_kwargs: (
            "```python\ndef divide_numbers(a, b):\n"
            "    return None if b == 0 else a / b\n```"
        ),
    )

    fixed = ai_code_fixer.fix(_context(), {})

    assert fixed.startswith("@healing_agent\ndef divide_numbers")
    assert "```" not in fixed
    compile(fixed, "<test-fix>", "exec")


def test_invalid_generated_code_is_rejected(monkeypatch):
    monkeypatch.setattr(
        ai_code_fixer,
        "get_ai_response",
        lambda *_args, **_kwargs: "this is not a function",
    )

    assert ai_code_fixer.fix(_context(), {}) is None
