"""
Unit tests for healing_agent.redactor — no API key / network required.

Run with:  python tests/test_redactor.py
"""

import os
import sys

# Make the package importable when run directly from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from healing_agent.redactor import redact, is_sensitive_name, get_sensitive_matcher


def test_sensitive_variable_values_are_redacted():
    context = {
        "variables": {
            "locals": {
                "password": {"type": "str", "value_preview": "hunter2"},
                "api_key": {"type": "str", "value_preview": "sk-secret123"},
                "username": {"type": "str", "value_preview": "alice"},
                "count": {"type": "int", "value_preview": "42"},
            }
        }
    }
    out = redact(context)
    locals_ = out["variables"]["locals"]
    assert locals_["password"] == "<redacted>", locals_
    assert locals_["api_key"] == "<redacted>", locals_
    # Non-sensitive names keep their structure/value
    assert locals_["username"] == {"type": "str", "value_preview": "alice"}
    assert locals_["count"] == {"type": "int", "value_preview": "42"}


def test_http_auth_headers_are_redacted():
    context = {
        "error": {
            "http_details": {
                "request": {
                    "method": "POST",
                    "url": "https://api.example.com/v1",
                    "headers": {
                        "Authorization": "Bearer abc.def.ghi",
                        "api-key": "***REMOVED***",
                        "Content-Type": "application/json",
                        "Cookie": "session=deadbeef",
                    },
                    "body": "{}",
                }
            }
        }
    }
    out = redact(context)
    headers = out["error"]["http_details"]["request"]["headers"]
    assert headers["Authorization"] == "<redacted>"
    assert headers["api-key"] == "<redacted>"
    assert headers["Cookie"] == "<redacted>"
    # Structural / non-sensitive fields survive
    assert headers["Content-Type"] == "application/json"
    assert out["error"]["http_details"]["request"]["url"] == "https://api.example.com/v1"


def test_function_arguments_redacted_by_name():
    context = {
        "function_arguments": {
            "token": {"value": "topsecret", "type": "str"},
            "user_id": {"value": "1001", "type": "int"},
        }
    }
    out = redact(context)
    assert out["function_arguments"]["token"] == "<redacted>"
    assert out["function_arguments"]["user_id"] == {"value": "1001", "type": "int"}


def test_structural_keys_survive():
    """Keys the pipeline depends on must not be treated as secrets."""
    matcher = get_sensitive_matcher()
    for safe in ["file", "message", "type", "source_code", "function_name",
                 "line_number", "signature", "traceback", "module"]:
        assert not is_sensitive_name(safe, matcher), f"{safe} wrongly flagged sensitive"
    for secret in ["password", "API_KEY", "access_token", "client_secret",
                   "Authorization", "db_password", "SESSION_TOKEN"]:
        assert is_sensitive_name(secret, matcher), f"{secret} not flagged sensitive"


def test_master_switch_disables_redaction():
    context = {"password": {"value_preview": "hunter2"}}
    out = redact(context, {"REDACT_SECRETS": False})
    assert out == context


def test_custom_pattern_and_placeholder():
    context = {"adoszam": {"value_preview": "12345678"}, "name": {"value_preview": "x"}}
    cfg = {"REDACT_EXTRA_PATTERNS": ["adoszam"], "REDACT_PLACEHOLDER": "***"}
    out = redact(context, cfg)
    assert out["adoszam"] == "***"
    assert out["name"] == {"value_preview": "x"}


def test_nested_and_list_structures():
    context = {"items": [{"secret": "a"}, {"ok": "b"}], "tup": ("x", {"token": "t"})}
    out = redact(context)
    assert out["items"][0]["secret"] == "<redacted>"
    assert out["items"][1]["ok"] == "b"
    assert out["tup"][1]["token"] == "<redacted>"


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} redactor tests passed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
