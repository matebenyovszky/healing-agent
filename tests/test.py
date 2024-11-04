from healing_agent import healing_agent


@healing_agent
def buggy_function(a, b):
    try:
        if b == 0:
            raise ValueError(
                "Cannot divide by zero. Please provide a non-zero value for 'b'."
                )
        result = a / b
        return result
    except ValueError as e:
        print(f'Error: {e}')
        print('Function was called with:')
        print(f'a: {a} (type: {type(a).__name__})')
        print(f'b: {b} (type: {type(b).__name__})')
        return None
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
        return None


buggy_function(1, 0)
