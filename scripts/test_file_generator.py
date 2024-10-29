import os
import shutil

def setup_tests():
    """
    Sets up test files by copying example tests to the test directory.
    If test directory doesn't exist, creates it and copies all tests from examples.
    
    Returns:
        str: Path to the test directory
    """
    # Define source and target directories
    examples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'examples', 'tests')
    test_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')

    # Create test directory if it doesn't exist
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
        print(f"✓ Created test directory at: {test_dir}")
    
    # Copy all files from examples/tests to tests/
    if os.path.exists(examples_dir):
        for item in os.listdir(examples_dir):
            source = os.path.join(examples_dir, item)
            destination = os.path.join(test_dir, item)
            
            if os.path.isfile(source):
                shutil.copy2(source, destination)
                print(f"✓ Copied test file: {item}")
            elif os.path.isdir(source):
                shutil.copytree(source, destination, dirs_exist_ok=True)
                print(f"✓ Copied test directory: {item}")
    else:
        print("! Warning: examples/tests directory not found")
        
    print(f"\n♣ Test files setup complete. Tests located at: {test_dir}")
    return test_dir

if __name__ == "__main__":
    setup_tests()
