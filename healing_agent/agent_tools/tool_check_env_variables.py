# Experimental and not used.

import os

def get_environment_variables() -> dict:
    """
    Get all environment variables and return them as a dictionary.
    
    Returns:
        dict: Dictionary containing all environment variables as key-value pairs
    """
    env_vars = {}
    for key, value in os.environ.items():
        env_vars[key] = value
    return env_vars

if __name__ == "__main__":
    print(get_environment_variables())

