# Experimental and not used.

import os
import ast
import json
from typing import Dict, List, Optional, Union

def get_function_details(file_path: str) -> List[Dict[str, str]]:
    """
    Extract function names and docstrings from a Python file.
    
    Args:
        file_path: Path to the Python file
        
    Returns:
        List of dictionaries containing function names and their docstrings
    """
    functions = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
            
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                docstring = ast.get_docstring(node)
                functions.append({
                    "name": node.name,
                    "docstring": docstring if docstring else "No description available"
                })
    except Exception as e:
        print(f"Error parsing {file_path}: {str(e)}")
        return []
        
    return functions

def list_directory_contents(
    directory: str,
    recursive: bool = False,
    include_functions: bool = False
) -> Dict[str, Union[List[str], Dict[str, List[Dict[str, str]]]]]:
    """
    List all files in a directory with optional recursive search and Python function details.
    
    Args:
        directory: Path to the directory to scan
        recursive: Whether to scan subdirectories recursively
        include_functions: Whether to extract function details from Python files
        
    Returns:
        Dictionary containing:
            - files: List of all files
            - python_files: Dictionary of Python files and their function details (if include_functions=True)
    """
    
    if not os.path.exists(directory):
        raise ValueError(f"Directory {directory} does not exist")
        
    result = {
        "files": [],
        "python_files": {}
    }
    
    def scan_directory(path: str):
        for entry in os.scandir(path):
            if entry.is_file():
                file_path = os.path.relpath(entry.path, directory)
                result["files"].append(file_path)
                
                if include_functions and file_path.endswith('.py'):
                    functions = get_function_details(entry.path)
                    if functions:
                        result["python_files"][file_path] = functions
                        
            elif entry.is_dir() and recursive:
                scan_directory(entry.path)
                
    scan_directory(directory)
    
    # Sort files for consistent output
    result["files"].sort()
    
    return result

def get_directory_info(
    directory: str = ".",
    recursive: bool = False,
    include_functions: bool = False,
    pretty_print: bool = False
) -> str:
    """
    Get directory information in JSON format.
    
    Args:
        directory: Path to the directory to scan (defaults to current directory)
        recursive: Whether to scan subdirectories recursively
        include_functions: Whether to extract function details from Python files
        pretty_print: Whether to format the JSON output with indentation
        
    Returns:
        JSON string containing directory information
    """
    try:
        contents = list_directory_contents(
            directory,
            recursive=recursive,
            include_functions=include_functions
        )
        
        return json.dumps(contents, indent=2 if pretty_print else None)
        
    except Exception as e:
        error_response = {
            "error": str(e),
            "directory": directory
        }
        return json.dumps(error_response, indent=2 if pretty_print else None)
