import ast
from typing import Dict, List, Optional, Tuple

def decorator_checker(file_path: str) -> bool:
    """
    Checks and corrects healing_agent decorator usage in Python files.
    
    Args:
        file_path (str): Path to the Python file to check
        
    Returns:
        bool: True if changes were made, False otherwise
    """
    try:
        # Read the file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Parse the content into an AST
        tree = ast.parse(content)
        
        changes_needed = False
        function_data: List[Tuple[int, int, bool, str]] = [] # (start, end, needs_decorator, function_name)
        
        # First pass - collect function info
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == 'main':
                    continue
                    
                start_line = node.lineno
                end_line = node.end_lineno
                has_healing_decorator = False
                
                # Check existing decorators
                if hasattr(node, 'decorator_list'):
                    decorator_count = 0
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Name) and dec.id == 'healing_agent':
                            decorator_count += 1
                            has_healing_decorator = True
                            
                    # Multiple healing_agent decorators found
                    if decorator_count > 1:
                        changes_needed = True
                        function_data.append((start_line, end_line, False, node.name))
                        print(f"♣ Function {node.name} has multiple healing_agent decorators")
                    # No healing_agent decorator found
                    elif decorator_count == 0:
                        changes_needed = True
                        function_data.append((start_line, end_line, True, node.name))
                        print(f"♣ Function {node.name} missing healing_agent decorator")
                    # Exactly one healing_agent decorator - no change needed
                    else:
                        function_data.append((start_line, end_line, False, node.name))
                else:
                    # No decorators at all
                    changes_needed = True
                    function_data.append((start_line, end_line, True, node.name))
                    print(f"♣ Function {node.name} missing healing_agent decorator")
        
        if not changes_needed:
            print("♣ All functions have correct healing_agent decorator usage")
            return False
            
        # Second pass - make corrections
        lines = content.split('\n')
        new_lines = []
        i = 0
        
        while i < len(lines):
            should_add = True
            for start, end, needs_decorator, func_name in function_data:
                if i == start - 1:  # Line before function def
                    # Remove extra healing_agent decorators if present
                    while i > 0 and lines[i-1].strip().startswith('@healing_agent'):
                        i -= 1
                        new_lines.pop()
                    
                    # Add single healing_agent decorator if needed
                    if needs_decorator:
                        new_lines.append('@healing_agent')
                        
                    break
                    
            if should_add:
                new_lines.append(lines[i])
            i += 1
            
        # Write back the corrected content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
            
        print("♣ Successfully updated healing_agent decorators")
        return True
        
    except Exception as e:
        print(f"♣ Error checking/correcting decorators: {str(e)}")
        return False

def build_replacement_source(
    context: Dict, fixed_code: str
) -> Optional[Tuple[str, str]]:
    """Build the smallest source-file replacement without writing it."""
    file_path = context['error']['file']
    function_name = context['function_info']['name']

    if not all([file_path, function_name, fixed_code]):
        print("♣ Missing required parameters for code replacement")
        return None

    with open(file_path, 'r', encoding='utf-8') as file:
        source = file.read()
    tree = ast.parse(source)

    fixed_tree = ast.parse(fixed_code)
    if len(fixed_tree.body) != 1 or not isinstance(
        fixed_tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        print("♣ Fixed code must contain exactly one function definition")
        return None
    fixed_function = fixed_tree.body[0]
    if fixed_function.name != function_name:
        print(
            f"♣ Fixed function name {fixed_function.name} does not match "
            f"{function_name}"
        )
        return None

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == function_name
        ):
            start_line = min(
                [node.lineno] + [decorator.lineno for decorator in node.decorator_list]
            )
            end_line = node.end_lineno
            break
    else:
        print(f"♣ Could not find function {function_name} in {file_path}")
        return None

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
    replacement = '\n'.join(fixed_lines) + '\n'

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
        print(f"♣ Error updating file: {str(e)}")
        print(f"♣ Error type: {type(e).__name__}")
        print(f"♣ Error details: {repr(e)}")
        return False
