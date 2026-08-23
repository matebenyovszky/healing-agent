"""The artifact savers must degrade, not mask the application's exception.

Both savers run inside the healing path, after the application has already
failed. Anything they raise travels instead of the original error, which is the
one guarantee this project makes unconditionally.
"""

from healing_agent import ai_fix_saver, exception_saver


def _context(tmp_path):
    return {
        "error": {
            "file": str(tmp_path / "app.py"),
            "type": "ZeroDivisionError",
            "message": "division by zero",
        },
        "function_info": {"name": "compute"},
        "fixed_code": "def compute():\n    return 1\n",
        "ai_hint": "guard the divisor",
    }


def test_saved_fix_header_carries_the_real_error(tmp_path):
    # Regression: the saver used to read 'error_type'/'error_message', which
    # capture_context never produces, so every header read "Unknown".
    path = ai_fix_saver.save_ai_fix(_context(tmp_path))

    assert path is not None
    header = open(path, encoding="utf-8").read()
    assert "# Error type: ZeroDivisionError" in header
    assert "# Error message: division by zero" in header
    assert "Unknown" not in header


def test_exception_saver_writes_and_returns_the_path(tmp_path):
    path = exception_saver.save_context(_context(tmp_path))

    assert path is not None and path.endswith("_compute.json")


def test_exception_saver_returns_none_instead_of_raising(tmp_path):
    # Regression: `return file_path` sat after the outer except, so a failure
    # before the assignment raised UnboundLocalError out of the healing path.
    assert exception_saver.save_context({}) is None
    assert exception_saver.save_context({"error": {}}) is None
    assert exception_saver.save_context({"error": {"file": None}}) is None


def test_ai_fix_saver_returns_none_instead_of_raising():
    assert ai_fix_saver.save_ai_fix({}) is None
    assert ai_fix_saver.save_ai_fix({"error": {}}) is None
