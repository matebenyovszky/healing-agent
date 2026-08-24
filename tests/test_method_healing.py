"""Repairs must reach methods, not only module-level functions.

Locating a definition by its bare name is not enough: `Loader.load` and a
module-level `load` are different functions with the same `__name__`, a method
lives at its class's indentation rather than at column zero, and a method is
not a name the reloaded module exposes. Each of those was a separate reason a
method could never be healed.
"""

import ast
import importlib.util
import sys
import textwrap

import pytest

from healing_agent import code_replacer
from healing_agent.code_replacer import (
    build_replacement_source,
    find_function_node,
    iter_function_nodes,
)

healing_module = importlib.import_module("healing_agent.healing_agent")
exception_handler = importlib.import_module("healing_agent.exception_handler")


SOURCE = '''\
def keep_me(x):
    return x


class Loader:
    """Docstring stays."""

    PREFIX = "row"

    def load(self, rows):
        return sum(int(r["amount"]) for r in rows)

    async def fetch(self, url):
        return url

    @classmethod
    def build(cls, rows):
        return cls()

    @staticmethod
    def parse(text):
        return int(text)

    class Inner:
        def deep(self, value):
            return value


def load(rows):
    """Same NAME as the method, a different function entirely."""
    return len(rows)


def outer():
    def load(rows):
        return -1
    return load
'''


def _context(tmp_path, name, qualname, line_hint=None, file_name="sample.py"):
    path = tmp_path / file_name
    if not path.exists():
        path.write_text(SOURCE, encoding="utf-8")
    return {
        "error": {"file": str(path)},
        "function_info": {
            "name": name,
            "qualname": qualname,
            "starting_line_number": line_hint,
        },
    }


# --- locating the definition -------------------------------------------------


def test_qualnames_match_what_python_builds():
    tree = ast.parse(SOURCE)
    found = dict(iter_function_nodes(tree))

    assert "Loader.load" in found
    assert "Loader.fetch" in found
    assert "Loader.Inner.deep" in found
    assert "load" in found
    assert "outer.<locals>.load" in found


def test_a_method_is_not_confused_with_a_module_level_function():
    tree = ast.parse(SOURCE)

    method = find_function_node(tree, "Loader.load", "load")
    plain = find_function_node(tree, "load", "load")

    assert method is not plain
    assert method.col_offset == 4 and plain.col_offset == 0


def test_async_methods_are_found():
    node = find_function_node(ast.parse(SOURCE), "Loader.fetch", "fetch")

    assert isinstance(node, ast.AsyncFunctionDef)


def test_nested_classes_are_found():
    node = find_function_node(ast.parse(SOURCE), "Loader.Inner.deep", "deep")

    assert node is not None and node.col_offset == 8


def test_a_missing_function_resolves_to_none():
    assert find_function_node(ast.parse(SOURCE), "Loader.absent", "absent") is None


def test_an_ambiguous_qualname_is_refused_unless_a_line_settles_it():
    conditional = textwrap.dedent('''\
        import sys

        if sys.platform == "win32":
            def load(rows):
                return 1
        else:
            def load(rows):
                return 2
        ''')
    tree = ast.parse(conditional)

    # Rewriting the wrong branch is worse than not repairing at all.
    assert find_function_node(tree, "load", "load") is None
    # `starting_line_number` comes from the live module, so it settles it.
    assert find_function_node(tree, "load", "load", line_hint=4).lineno == 4
    assert find_function_node(tree, "load", "load", line_hint=7).lineno == 7


def test_a_context_without_a_qualname_still_resolves_by_name():
    # Older captured contexts, and decorators that rewrite __qualname__.
    tree = ast.parse("def only(x):\n    return x\n")

    assert find_function_node(tree, None, "only") is not None


# --- building the replacement ------------------------------------------------


def test_a_method_is_replaced_at_its_own_indentation(tmp_path):
    context = _context(tmp_path, "load", "Loader.load")
    candidate = 'def load(self, rows):\n    return 42\n'

    source, new_source = build_replacement_source(context, candidate)

    assert "    def load(self, rows):\n        return 42\n" in new_source
    compile(new_source, "sample.py", "exec")  # would raise on a bad indent
    # Everything else survives untouched.
    assert "def keep_me(x):\n    return x\n" in new_source
    assert '    """Docstring stays."""' in new_source
    assert '    PREFIX = "row"' in new_source


def test_the_same_named_module_function_is_left_alone(tmp_path):
    context = _context(tmp_path, "load", "Loader.load")

    _, new_source = build_replacement_source(
        context, 'def load(self, rows):\n    return 42\n'
    )

    assert '"""Same NAME as the method, a different function entirely."""' in new_source
    assert "return len(rows)" in new_source, "the module-level load was overwritten"


def test_a_candidate_that_arrives_indented_is_normalised(tmp_path):
    context = _context(tmp_path, "load", "Loader.load")
    # A model shown an indented method often answers with an indented method.
    candidate = '    def load(self, rows):\n        return 42\n'

    _, new_source = build_replacement_source(context, candidate)

    assert "    def load(self, rows):\n        return 42\n" in new_source
    compile(new_source, "sample.py", "exec")


def test_module_level_functions_are_unaffected(tmp_path):
    context = _context(tmp_path, "keep_me", "keep_me")

    _, new_source = build_replacement_source(
        context, 'def keep_me(x):\n    return x * 2\n'
    )

    assert "def keep_me(x):\n    return x * 2\n" in new_source
    assert new_source.count("class Loader:") == 1
    compile(new_source, "sample.py", "exec")


def test_an_async_method_is_replaced(tmp_path):
    context = _context(tmp_path, "fetch", "Loader.fetch")

    _, new_source = build_replacement_source(
        context, 'async def fetch(self, url):\n    return url.strip()\n'
    )

    assert "    async def fetch(self, url):\n        return url.strip()\n" in new_source
    compile(new_source, "sample.py", "exec")


def test_a_method_in_a_nested_class_is_replaced(tmp_path):
    context = _context(tmp_path, "deep", "Loader.Inner.deep")

    _, new_source = build_replacement_source(
        context, 'def deep(self, value):\n    return value + 1\n'
    )

    assert "        def deep(self, value):\n            return value + 1\n" in new_source
    compile(new_source, "sample.py", "exec")


def test_a_decorated_method_keeps_its_original_decorators(tmp_path):
    decorated = textwrap.dedent('''\
        import healing_agent

        class Loader:
            @healing_agent(MAX_ATTEMPTS=5)
            def load(self, rows):
                return rows["missing"]
        ''')
    path = tmp_path / "decorated.py"
    path.write_text(decorated, encoding="utf-8")
    context = {
        "error": {"file": str(path)},
        "function_info": {"name": "load", "qualname": "Loader.load"},
    }

    _, new_source = build_replacement_source(
        context, '@healing_agent\ndef load(self, rows):\n    return 0\n'
    )

    # The original decorator carries an argument the candidate does not know
    # about, and must not be duplicated by the one the candidate brought.
    assert new_source.count("@healing_agent") == 1
    assert "    @healing_agent(MAX_ATTEMPTS=5)\n" in new_source
    assert "    def load(self, rows):\n        return 0\n" in new_source
    compile(new_source, "decorated.py", "exec")


def test_a_classmethod_keeps_its_decorator_and_indentation(tmp_path):
    context = _context(tmp_path, "build", "Loader.build")

    _, new_source = build_replacement_source(
        context, 'def build(cls, rows):\n    return cls\n'
    )

    assert "    @classmethod\n    def build(cls, rows):\n        return cls\n" in new_source
    compile(new_source, "sample.py", "exec")


def test_an_unfindable_target_refuses_rather_than_guessing(tmp_path, capsys):
    context = _context(tmp_path, "absent", "Loader.absent")

    assert build_replacement_source(context, 'def absent(self):\n    return 1\n') is None


# --- resolving the repaired function after the reload ------------------------


RELOADABLE = textwrap.dedent('''\
    class Loader:
        def load(self, rows):
            return "method"

        @classmethod
        def build(cls, rows):
            return "classmethod"

        @staticmethod
        def parse(text):
            return "staticmethod"

        class Inner:
            def deep(self):
                return "nested"

    def load(rows):
        return "module level"
    ''')


@pytest.fixture
def reloadable(tmp_path):
    path = tmp_path / "reloadable.py"
    path.write_text(RELOADABLE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("reloadable_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("reloadable_probe", None)


def test_resolve_finds_a_module_level_function(reloadable):
    resolved = healing_module._resolve_repaired(reloadable, "load", "load")

    assert resolved(["a"]) == "module level"


def test_resolve_walks_the_qualname_path_to_a_method(reloadable):
    resolved = healing_module._resolve_repaired(reloadable, "Loader.load", "load")

    assert resolved(reloadable.Loader(), []) == "method"


def test_resolve_reaches_a_nested_class(reloadable):
    resolved = healing_module._resolve_repaired(
        reloadable, "Loader.Inner.deep", "deep"
    )

    assert resolved(reloadable.Loader.Inner()) == "nested"


def test_resolve_returns_a_classmethod_unbound(reloadable):
    # The decorator wrapped the plain function, so the captured arguments
    # already carry `cls`. A bound method would receive it twice.
    resolved = healing_module._resolve_repaired(reloadable, "Loader.build", "build")

    assert resolved(reloadable.Loader, []) == "classmethod"


def test_resolve_returns_a_staticmethod_as_a_plain_function(reloadable):
    resolved = healing_module._resolve_repaired(reloadable, "Loader.parse", "parse")

    assert resolved("7") == "staticmethod"


# --- capture ------------------------------------------------------------------


def test_captured_method_source_is_valid_python(tmp_path):
    path = tmp_path / "captured.py"
    path.write_text(SOURCE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("captured_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        context = exception_handler.capture_context(
            func=module.Loader.load, args=(module.Loader(), [{"amount": 1}])
        )
        captured = context["function_info"]["source_code"]

        # The old capture dedented only the FIRST line, so what reached the
        # model could not even be parsed.
        ast.parse(captured)
        assert captured.startswith("def load(self, rows):")
        assert "sum(int(" in captured, "the module-level load was captured instead"
    finally:
        sys.modules.pop("captured_probe", None)


def test_capture_distinguishes_a_method_from_a_module_function(tmp_path):
    path = tmp_path / "distinct.py"
    path.write_text(SOURCE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("distinct_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        plain = exception_handler.capture_context(func=module.load, args=([],))

        assert "len(rows)" in plain["function_info"]["source_code"]
        assert plain["function_info"]["qualname"] == "load"
    finally:
        sys.modules.pop("distinct_probe", None)


# --- a full healing session on a method ---------------------------------------


METHOD_MODULE = '''\
import healing_agent


class Loader:
    def __init__(self, factor):
        self.factor = factor

    @healing_agent
    def load(self, rows):
        return sum(row["amount"] for row in rows) * self.factor
'''

REPAIRED_METHOD = (
    'def load(self, rows):\n'
    '    key = "amount" if "amount" in rows[0] else "osszeg"\n'
    '    return sum(row[key] for row in rows) * self.factor\n'
)


def test_a_method_is_healed_end_to_end(tmp_path, monkeypatch):
    module_path = tmp_path / "method_heal.py"
    module_path.write_text(METHOD_MODULE, encoding="utf-8")

    monkeypatch.setattr(
        healing_module,
        "load_config",
        lambda: (
            {
                "MAX_ATTEMPTS": 1,
                "AUTO_FIX": True,
                "AUTO_SYSCHANGE": False,
                "BACKUP_ENABLED": False,
                "RESTORE_ON_FAILURE": False,
                "SAVE_EXCEPTIONS": False,
                "SAVE_AI_FIXES": False,
                "DEBUG": False,
                "GIT_MODE": "off",
            },
            None,
        ),
    )
    monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "stub")
    monkeypatch.setattr(healing_module, "fix", lambda *_a, **_k: REPAIRED_METHOD)

    spec = importlib.util.spec_from_file_location("method_heal", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["method_heal"] = module
    spec.loader.exec_module(module)
    try:
        # Drifted input: the header is "osszeg", so the original method raises.
        result = module.Loader(2).load([{"osszeg": 10}, {"osszeg": 5}])

        assert result == 30, "the repaired method was not run with the original args"
        healed = module_path.read_text(encoding="utf-8")
        assert "    def load(self, rows):" in healed
        assert "    @healing_agent\n" in healed
        assert "        self.factor = factor" in healed, "the class body was damaged"
        compile(healed, str(module_path), "exec")
    finally:
        sys.modules.pop("method_heal", None)


NESTED_MODULE = '''\
import healing_agent


def outer(rows):
    @healing_agent
    def inner(payload):
        return payload["missing"]

    return inner(rows)
'''


def test_a_nested_function_is_refused_before_the_file_is_touched(
    tmp_path, monkeypatch, capsys
):
    module_path = tmp_path / "nested_heal.py"
    module_path.write_text(NESTED_MODULE, encoding="utf-8")
    before = module_path.read_bytes()

    monkeypatch.setattr(
        healing_module,
        "load_config",
        lambda: (
            {
                "MAX_ATTEMPTS": 1,
                "AUTO_FIX": True,
                "AUTO_SYSCHANGE": False,
                "BACKUP_ENABLED": False,
                "RESTORE_ON_FAILURE": False,
                "SAVE_EXCEPTIONS": False,
                "SAVE_AI_FIXES": False,
                "DEBUG": False,
                "GIT_MODE": "off",
            },
            None,
        ),
    )
    monkeypatch.setattr(healing_module, "generate_hint", lambda *_a, **_k: "stub")
    monkeypatch.setattr(
        healing_module, "fix", lambda *_a, **_k: 'def inner(payload):\n    return 1\n'
    )

    spec = importlib.util.spec_from_file_location("nested_heal", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["nested_heal"] = module
    spec.loader.exec_module(module)
    try:
        with pytest.raises(KeyError):
            module.outer({})

        assert module_path.read_bytes() == before, (
            "a function that cannot be reloaded must not have its file rewritten"
        )
        assert "defined inside another function" in capsys.readouterr().out
    finally:
        sys.modules.pop("nested_heal", None)


def test_the_resolver_is_shared_by_capture_and_replacement():
    # One definition of "which function is this?" - capture and replacement
    # disagreeing is how a repair lands on the wrong function.
    assert exception_handler.find_function_node is code_replacer.find_function_node
