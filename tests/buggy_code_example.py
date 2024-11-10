try:
    import healing_agent
    print('Found healing_agent as module')
except ImportError as e:
    print(f'Cannot import healing_agent directly: {e}')
import random


@healing_agent
def divide_numbers(a=None, b=None):
    """Deliberately divides by zero sometimes"""
    import random
    if a is None:
        a = random.randint(1, 10)
    if b is None or b == 0:
        b = random.randint(1, 2)
    print(f'Attempting to divide {a} by {b}')
    try:
        return a / b
    except ZeroDivisionError:
        raise ValueError(
            'Cannot divide by zero. Please provide a non-zero value for b.'
            ) from None
    except Exception as e:
        raise RuntimeError(f'An unexpected error occurred: {e}') from None


@healing_agent
def access_list(index=None):
    import random
    """Deliberately tries to access an invalid list index"""
    my_list = [1, 2, 3]
    if index is None:
        index = random.randint(0, len(my_list) - 1)
    try:
        print(
            f'Attempting to access index {index} in list of length {len(my_list)}'
            )
        return my_list[index]
    except IndexError as e:
        print(
            f'Error: {e}. Invalid index {index} for list of length {len(my_list)}.'
            )


@healing_agent
def file_operations(filename='nonexistent_file.txt'):
    """Deliberately tries to read a non-existent file"""
    print(f'Attempting to read file: {filename}')
    try:
        with open(filename, 'r') as f:
            return f.read()
    except FileNotFoundError as e:
        print(
            f"Error: {e.strerror} - '{e.filename}'. Please ensure the file exists."
            )
        return None


@healing_agent
def type_conversion(value=None):
    """Deliberately tries invalid type conversions"""
    import random
    values = ['123', '456', 'abc', '789']
    if value is None:
        value = random.choice(values)
    print(f'Attempting to convert {value} to integer')
    try:
        return int(value)
    except ValueError as e:
        print(f'Error: {e}. The value "{value}" is not a valid integer.')
        return None


@healing_agent
def key_error_example(key=None):
    """Deliberately tries to access a missing key in a dictionary"""
    import random
    my_dict = {'a': 1, 'b': 2}
    if key is None:
        key = random.choice(['a', 'b', 'c'])
    print(f"Attempting to access key '{key}' in dictionary")
    try:
        return my_dict[key]
    except KeyError as e:
        print(
            f"KeyError: {str(e)} - The key '{key}' does not exist in the dictionary."
            )
        return None


@healing_agent
def index_error_example(index=None):
    """Deliberately tries to access an invalid index in a string"""
    import random
    my_string = 'hello'
    if index is None:
        index = random.randint(-10, 10)
    print(f"Attempting to access index {index} in string '{my_string}'")
    try:
        if index < 0 or index >= len(my_string):
            raise IndexError('Index is out of range for the string.')
        return my_string[index]
    except IndexError as e:
        print(
            f'Error: {e}. Provided index: {index}. Valid range: 0 to {len(my_string) - 1}.'
            )
        return None


@healing_agent
def attribute_error_example():
    """Deliberately tries to access a non-existent attribute"""


    class MyClass:

        def __init__(self):
            self.attr = 'This is an existing attribute'
    obj = MyClass()
    print("Attempting to access attribute 'attr'")
    try:
        return obj.attr
    except AttributeError as e:
        print(f'An error occurred: {e}')
        print(f'Detailed Error Information: {e.args}')
        print(f'Trying to access a non-existent attribute on {obj}')


def main():
    """Run all error-prone functions in sequence"""
    print('♣ Testing functions')
    a = 10
    functions = [divide_numbers, divide_numbers(a, b=0), access_list,
        file_operations, type_conversion, key_error_example,
        index_error_example, attribute_error_example]
    for func in functions:
        try:
            print(f'\nTesting function: {func.__name__}')
            print('Testing function: ♣ ')
            result = func()
            print(f'Result: {result}')
        except Exception as e:
            print(f'Caught exception: {str(e)}')
        print('-' * 50)


if __name__ == '__main__':
    main()
