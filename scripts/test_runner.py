import os
import importlib.util
import sys

def run_tests():
    """
    Runs all Python test files in the tests directory.
    Prints results and any errors encountered.
    """
    # Get path to tests directory relative to this script
    tests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')
    
    if not os.path.exists(tests_dir):
        print(f"! Error: Tests directory not found at {tests_dir}")
        return

    print(f"\n♣ Running tests from: {tests_dir}\n")
    
    # Track test results
    total_tests = 0
    failed_tests = 0
    
    # Find and run all .py files in tests directory
    for filename in os.listdir(tests_dir):
        if filename.endswith('.py'):
            total_tests += 1
            test_path = os.path.join(tests_dir, filename)
            
            print(f"Running test: {filename}")
            print("-" * 50)
            
            try:
                # Import and run main() for all test files
                spec = importlib.util.spec_from_file_location(
                    filename[:-3], test_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[filename[:-3]] = module
                spec.loader.exec_module(module)
                
                # Look for and run main() if it exists
                if hasattr(module, 'main'):
                    module.main()
                
            except Exception as e:
                failed_tests += 1
                print(f"\n! Error in {filename}:")
                print(f"  {str(e)}")
                print(f"  {type(e).__name__}")
            
            print("\n")

    # Print summary
    print("=" * 50)
    print(f"Test Summary:")
    print(f"Total tests: {total_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Passed: {total_tests - failed_tests}")
    print("=" * 50)

if __name__ == "__main__":
    try:
        run_tests()
        print("\n✓ All test suites completed")
    except Exception as e:
        print(f"\n✗ Test execution failed: {str(e)}")
        raise
