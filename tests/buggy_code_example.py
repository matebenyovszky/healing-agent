try:
    import healing_agent
    print('Found healing_agent as module')
    print(f'Module location: {healing_agent.__file__}')
except ImportError as e:
    print(f'Cannot import healing_agent directly: {e}')
try:
    from healing_agent import healing_agent
    print('Successfully imported healing_agent decorator')
except ImportError as e:
    print(f'Cannot import healing_agent.healing_agent: {e}')
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
    if b == 0:
        return 'Error: Cannot divide by zero'
    return a / b


@healing_agent
def access_list(index=None):
    """Deliberately tries to access an invalid list index"""
    import random
    my_list = [1, 2, 3]
    if index is None:
        index = random.randint(0, len(my_list) - 1)
    print(
        f'Attempting to access index {index} in list of length {len(my_list)}')
    if index < 0 or index >= len(my_list):
        raise IndexError('Index is out of range')
    return my_list[index]


@healing_agent
def file_operations(filename='nonexistent_file.txt'):
    """Deliberately tries to read a non-existent file"""
    print(f'Attempting to read file: {filename}')
    with open(filename, 'r') as f:
        return f.read()


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
    except ValueError:
        return f'Error: cannot convert {value} to integer'


@healing_agent
def key_error_example(key=None):
    """Deliberately tries to access a missing key in a dictionary"""
    import random
    my_dict = {'a': 1, 'b': 2}
    if key is None:
        key = random.choice(['a', 'b', 'c'])
    print(f"Attempting to access key '{key}' in dictionary")
    return my_dict.get(key, f"Error: Key '{key}' not found in dictionary"
        ) if key in my_dict else f"Error: Key '{key}' not found in dictionary"


@healing_agent
def index_error_example(index=None):
    """Deliberately tries to access an invalid index in a string"""
    import random
    my_string = 'hello'
    if index is None:
        index = random.randint(-10, 10)
    print(f"Attempting to access index {index} in string '{my_string}'")
    try:
        if index < 0:
            index += len(my_string)
        return my_string[index]
    except IndexError:
        return 'Error: Index is out of range'


@healing_agent
def attribute_error_example():
    """Deliberately tries to access a non-existent attribute"""


    class MyClass:
        pass
    obj = MyClass()
    print("Attempting to access non-existent attribute 'attr'")
    try:
        return getattr(obj, 'attr')
    except AttributeError:
        return "Error: Attribute 'attr' does not exist"


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
