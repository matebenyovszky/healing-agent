import ast
import astor
from typing import List, Tuple, Dict, Optional

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

def function_replacer(context: Dict, fixed_code: str) -> bool:
    """
    Updates the original file by replacing the buggy function with the fixed code using AST.
    
    Args:
        context (Dict): Contains information about the bug context including:
            - file_path: Path to the original file
            - function_name: Name of the function to replace
            - original_code: Original function code
        fixed_code (str): The new code to replace the buggy function with
        config (Optional[Dict]): Configuration parameters (unused for now)
        
    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:

        file_path = context['error']['file']
        function_name = context['function_info']['name']
        
        if not all([file_path, function_name, fixed_code]):
            print("♣ Missing required parameters for code replacement")
            return False

        # Parse the original file
        with open(file_path, 'r', encoding='utf-8') as file:
            source = file.read()
        tree = ast.parse(source)

        # Parse the fixed code
        fixed_tree = ast.parse(fixed_code)
        if not isinstance(fixed_tree.body[0], ast.FunctionDef):
            print("♣ Fixed code does not contain a function definition")
            return False
        fixed_function = fixed_tree.body[0]

        # Find and replace the function in the original AST
        for i, node in enumerate(tree.body):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                tree.body[i] = fixed_function
                break
        else:
            print(f"♣ Could not find function {function_name} in {file_path}")
            return False

        # Convert modified AST back to source code
        new_source = astor.to_source(tree)

        # Write the updated content back to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(new_source)

        return True

    except Exception as e:
        print(f"♣ Error updating file: {str(e)}")
        print(f"♣ Error type: {type(e).__name__}")
        print(f"♣ Error details: {repr(e)}")
        return False
