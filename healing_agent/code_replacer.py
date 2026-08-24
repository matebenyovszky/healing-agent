import ast
import logging
import textwrap
from typing import Dict, Iterator, Optional, Tuple
from .console import emit

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def node_start_line(node: ast.AST) -> int:
    """First source line of a definition, decorators included."""
    return min([node.lineno] + [d.lineno for d in node.decorator_list])


def iter_function_nodes(node: ast.AST, prefix: str = "") -> Iterator[Tuple[str, ast.AST]]:
    """Yield ``(qualname, node)`` for every function defined below ``node``.

    Qualnames are built the way Python builds ``__qualname__``: a class adds its
    own name, and a function adds its name plus ``<locals>`` for anything nested
    inside it. That makes the tree directly comparable with the qualname the
    captured context already carries, which is what makes a method findable at
    all — a bare name cannot tell ``Loader.load`` from a module-level ``load``.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            yield from iter_function_nodes(child, f"{prefix}{child.name}.")
        elif isinstance(child, _FUNCTION_NODES):
            qualname = f"{prefix}{child.name}"
            yield qualname, child
            yield from iter_function_nodes(child, f"{qualname}.<locals>.")
        else:
            # if/try/with bodies are the same scope, so the prefix carries over.
            yield from iter_function_nodes(child, prefix)


def find_function_node(
    tree: ast.AST,
    qualname: Optional[str] = None,
    name: Optional[str] = None,
    line_hint: Optional[int] = None,
) -> Optional[ast.AST]:
    """Locate the definition a repair targets, or None if it is not unambiguous.

    Ambiguity answers None deliberately. The same qualname can appear twice —
    two branches of an ``if`` each defining it — and rewriting the wrong one is
    worse than not repairing at all: a caller that gets None re-raises the
    application's original exception, which is always a safe outcome.
    """
    found = list(iter_function_nodes(tree))

    matches = [node for found_name, node in found if qualname and found_name == qualname]
    if not matches and name:
        # A context captured before qualnames were recorded, or a decorator that
        # rewrote __qualname__: fall back to the bare name.
        matches = [node for _, node in found if node.name == name]

    if len(matches) > 1 and line_hint:
        # `starting_line_number` is captured from the live module, so it settles
        # conditional definitions that share a qualname. Both readings are
        # accepted because the capture path excludes decorators and the splice
        # path includes them.
        narrowed = [
            node for node in matches
            if line_hint in (node.lineno, node_start_line(node))
        ]
        if narrowed:
            matches = narrowed

    return matches[0] if len(matches) == 1 else None


def build_replacement_source(
    context: Dict, fixed_code: str
) -> Optional[Tuple[str, str]]:
    """Build the smallest source-file replacement without writing it."""
    file_path = context['error']['file']
    function_info = context['function_info']
    function_name = function_info['name']
    qualname = function_info.get('qualname')
    line_hint = function_info.get('starting_line_number')

    if not all([file_path, function_name, fixed_code]):
        emit("♣ Missing required parameters for code replacement")
        return None

    with open(file_path, 'r', encoding='utf-8') as file:
        source = file.read()
    tree = ast.parse(source)

    # A candidate for a method is often generated at the indentation it was
    # shown at. Normalising here means the parse below sees module-level code
    # whatever the model produced, and the splice re-indents it to the column
    # the original definition actually occupies.
    fixed_code = textwrap.dedent(fixed_code)

    fixed_tree = ast.parse(fixed_code)
    if len(fixed_tree.body) != 1 or not isinstance(
        fixed_tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        emit("♣ Fixed code must contain exactly one function definition")
        return None
    fixed_function = fixed_tree.body[0]
    if fixed_function.name != function_name:
        emit(
            f"♣ Fixed function name {fixed_function.name} does not match "
            f"{function_name}"
        )
        return None

    node = find_function_node(tree, qualname, function_name, line_hint)
    if node is None:
        emit(
            f"♣ Could not locate {qualname or function_name} in {file_path}",
            level=logging.ERROR,
        )
        return None
    start_line = node_start_line(node)
    end_line = node.end_lineno

    source_lines = source.splitlines(keepends=True)

    # Preserve the ORIGINAL decorator lines: they may carry arguments such as
    # @healing_agent(MAX_ATTEMPTS=5) that the generated replacement does not
    # know about. Drop any healing_agent decorator the generated code brought
    # along so the original one is not duplicated.
    original_decorator_lines = source_lines[start_line - 1 : node.lineno - 1]
    original_has_healing = any(
        line.strip().startswith('@healing_agent') for line in original_decorator_lines
    )
    fixed_lines = fixed_code.rstrip().splitlines()
    while (
        original_has_healing
        and fixed_lines
        and fixed_lines[0].strip().startswith('@healing_agent')
    ):
        fixed_lines.pop(0)

    # A method lives at its class's indentation. The candidate was normalised to
    # column zero above, so it is put back at the column the original occupied;
    # blank lines are left blank rather than filled with trailing whitespace.
    replacement = textwrap.indent(
        '\n'.join(fixed_lines) + '\n', ' ' * node.col_offset
    )

    new_source = ''.join(
        source_lines[: start_line - 1]
        + original_decorator_lines
        + [replacement]
        + source_lines[end_line:]
    )
    compile(new_source, file_path, 'exec')
    return source, new_source


def function_replacer(context: Dict, fixed_code: str) -> bool:
    """
    Update the original file with the minimal replacement built from AST lines.
    
    Args:
        context (Dict): Contains information about the bug context including:
            - file_path: Path to the original file
            - function_name: Name of the function to replace
            - original_code: Original function code
        fixed_code (str): The new code to replace the buggy function with
    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:

        replacement = build_replacement_source(context, fixed_code)
        if replacement is None:
            return False
        _, new_source = replacement
        file_path = context['error']['file']

        # Write the updated content back to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(new_source)

        return True

    except Exception as e:
        emit(f"♣ Error updating file: {str(e)}", level=logging.ERROR)
        emit(f"♣ Error type: {type(e).__name__}")
        emit(f"♣ Error details: {repr(e)}")
        return False
