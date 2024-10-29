import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from healing_agent.code_fixer import fix
from healing_agent.load_config import load_config
def test_code_fixer():
    """Test the code fixer."""
    # Test context
    test_context = {
        'original_code': '''def divide_numbers(a, b):
    return a/b''',
        'error_info': {
            'type': 'ZeroDivisionError',
            'message': 'division by zero',
            'traceback': 'Traceback (most recent call last):\n  File "<string>", line 2, in divide_numbers\nZeroDivisionError: division by zero'
        },
        'function_info': {
            'name': 'divide_numbers',
            'signature': 'divide_numbers(a, b)',
            'module': 'test_module'
        },
        'function_arguments': {
            'a': {'value': 10, 'type': 'int'},
            'b': {'value': 0, 'type': 'int'}
        }
    }
    
    # Load config
    config = load_config()

    # Try fixing the code
    fixed_code = fix(test_context, config)
    print("\n♣ Fixed code:")
    print(fixed_code)

if __name__ == "__main__":
    test_code_fixer()
