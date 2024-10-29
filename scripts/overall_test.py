import os
import subprocess
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from scripts.test_runner import run_tests as execute_tests

def create_package():
    """Create the package using setuptools."""
    print("♣ Creating package...")
    subprocess.run(["python", "setup.py", "sdist"], check=True)
    print("♣ Package created successfully.")

def uninstall_previous_version():
    """Uninstall any previous version of the package."""
    print("♣ Uninstalling previous version of the package...")
    subprocess.run(["pip", "uninstall", "-y", "healing_agent"], check=True)
    print("♣ Previous version uninstalled successfully.")

def install_package():
    """Install the package."""
    print("♣ Installing the package...")
    # Install in editable mode for development
    subprocess.run(["pip", "install", "-e", "."], check=True)
    # Verify installation
    print("♣ Verifying installation...")
    result = subprocess.run(["pip", "show", "healing_agent"], capture_output=True, text=True)
    print(result.stdout)
    print("♣ Package installed successfully.")

def check_configuration():
    """Check the configuration settings by running the configurator."""
    print("♣ Checking configuration...")
    try:
        from healing_agent.configurator import setup_config
        config_path = setup_config()  # Run the setup_config function
        print(f"♣ Configuration settings are valid. Using config file at: {config_path}")
    except Exception as e:
        print(f"♣ Configuration error: {str(e)}")

def run_test_file_generator():
    """Run the test file generator."""
    print("♣ Generating test files...")
    # Assuming the test file generator is a script named 'generate_tests.py'
    subprocess.run(["python", "scripts/test_file_generator.py"], check=True)
    print("♣ Test files generated successfully.")

def run_tests():
    """Run all tests using the test runner."""
    print("♣ Running all tests...")
    execute_tests()

def main():
    """Main function to orchestrate the package management and testing."""
    create_package()
    uninstall_previous_version()
    install_package()
    check_configuration()
    run_test_file_generator()
    run_tests()

if __name__ == "__main__":
    main()
