import json
from unittest.mock import Mock
from healing_agent import healing_agent
valid_json = '{"name": "John", "age": 30}'
missing_brace = '{"name": "John", "age": 30'
extra_comma = '{"name": "John", "age": 30,}'
invalid_quotes = "{'name': 'John', 'age': 30}"
invalid_json = 'not json at all'
unclosed_array = '[1,2,3'
null_json = None
empty_json = ''
invalid_boolean = '{"flag": True}'
trailing_chars = '{"name": "John"} extra stuff'


@healing_agent
def fetch_data(response_json):
    import json
    from unittest.mock import Mock
    response = Mock()
    response.text = response_json
    if response.text is None:
        print('Error: response_json is None')
        return None
    if response.text.strip() == '':
        print('Error: response_json is empty')
        return None
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as e:
        print(f'JSON Decode Error: {e}')
        return None
    except Exception as e:
        print(f'Unexpected error: {e}')
        return None
    if isinstance(data, dict) and 'flag' not in data:
        print('Error: flag key not found in the data')
        return None
    return data


def main():
    test_cases = [('Valid JSON', valid_json), ('Missing Brace',
        missing_brace), ('Extra Comma', extra_comma), ('Invalid Quotes',
        invalid_quotes), ('Invalid JSON', invalid_json), ('Unclosed Array',
        unclosed_array), ('Null JSON', null_json), ('Empty JSON',
        empty_json), ('Invalid Boolean', invalid_boolean), (
        'Trailing Characters', trailing_chars)]
    for test_name, test_json in test_cases:
        print(f'\nTest Case - {test_name}:')
        try:
            result = fetch_data(test_json)
            print('Result:', result)
        except Exception as e:
            print('Error:', str(e))


if __name__ == '__main__':
    main()
