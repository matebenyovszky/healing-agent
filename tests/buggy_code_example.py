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
    if b is None:
        b = random.randint(0, 2)
    print(f'Attempting to divide {a} by {b}')
    try:
        result = a / b
    except ZeroDivisionError as e:
        print(f'Error: {e}. Cannot divide by zero. Returning None.')
        return None
    return result


@healing_agent
def access_list(index=None):
    """Deliberately tries to access an invalid list index"""
    my_list = [1, 2, 3]
    if index is None:
        index = random.randint(0, 5)
    print(
        f'Attempting to access index {index} in list of length {len(my_list)}')
    return my_list[index]


@healing_agent
def file_operations(filename='nonexistent_file.txt'):
    """Deliberately tries to read a non-existent file"""
    print(f'Attempting to read file: {filename}')
    try:
        with open(filename, 'r') as f:
            return f.read()
    except FileNotFoundError as e:
        print(
            f'Error: {e.strerror}. Please check if the file exists at the specified path: {filename}.'
            )


@healing_agent
def type_conversion(value=None):
    """Deliberately tries invalid type conversions"""
    values = ['123', '456', 'abc', '789']
    if value is None:
        value = random.choice(values)
    print(f'Attempting to convert {value} to integer')
    return int(value)


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
    except KeyError:
        print(f"KeyError: The key '{key}' does not exist in the dictionary.")
        print(f'Available keys are: {list(my_dict.keys())}')
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
        return my_string[index]
    except IndexError as e:
        print(
            f'Error: {e}. Index {index} is out of range. Valid range is 0 to {len(my_string) - 1}.'
            )
        return None


@healing_agent
def attribute_error_example():
    """Deliberately tries to access a non-existent attribute"""


    class MyClass:

        def __init__(self):
            self.attr = None
    obj = MyClass()
    print("Attempting to access 'attr'")
    try:
        return obj.attr
    except AttributeError as e:
        print(f'AttributeError: {e.args[0]}')
        print(f"Error details - Object: {obj}, Expected attribute: 'attr'")


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
