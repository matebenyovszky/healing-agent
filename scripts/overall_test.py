import os
import subprocess
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from scripts.test_runner import run_tests as execute_tests

def install_package(package):
    """Install a Python package using pip."""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"♣ Successfully installed {package}")
    except subprocess.CalledProcessError:
        print(f"♣ Failed to install {package}")
        sys.exit(1)

def check_and_install_prerequisites():
    """Check and install all required packages."""
    required_packages = [
        'build',
        'hatchling',
        'twine'
    ]
    
    print("♣ Checking prerequisites...")
    for package in required_packages:
        try:
            __import__(package)
            print(f"♣ {package} is already installed")
        except ImportError:
            print(f"♣ Installing {package}...")
            install_package(package)

def create_package():
    """Create the package using build module."""
    print("♣ Creating package...")
    try:
        # Clean previous builds
        dist_dir = Path('dist')
        if dist_dir.exists():
            import shutil
            shutil.rmtree(dist_dir)
        
        # Build the package
        subprocess.run([sys.executable, "-m", "build"], check=True)
        print("♣ Package created successfully.")
    except subprocess.CalledProcessError as e:
        print(f"♣ Failed to create package: {e}")
        sys.exit(1)

def uninstall_previous_version():
    """Uninstall any previous version of the package."""
    print("♣ Uninstalling previous version of the package...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "healing_agent"], check=True)
        print("♣ Previous version uninstalled successfully.")
    except subprocess.CalledProcessError:
        print("♣ No previous version found or failed to uninstall.")

def install_package_local():
    """Install the package in development mode."""
    print("♣ Installing the package...")
    try:
        # Install in editable mode for development
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], check=True)
        
        # Verify installation
        print("♣ Verifying installation...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "healing_agent"], 
            capture_output=True, 
            text=True
        )
        print(result.stdout)
        print("♣ Package installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"♣ Failed to install package: {e}")
        sys.exit(1)

def check_configuration():
    """Check the configuration settings by running the configurator."""
    print("♣ Checking configuration...")
    try:
        from healing_agent.configurator import setup_config
        config_path = setup_config()
        print(f"♣ Configuration settings are valid. Using config file at: {config_path}")
    except Exception as e:
        print(f"♣ Configuration error: {str(e)}")
        #print(f"♣ Error traceback: {traceback.format_exc()}")

def run_test_file_generator():
    """Run the test file generator."""
    print("♣ Generating test files...")
    try:
        subprocess.run([sys.executable, "scripts/test_file_generator.py"], check=True)
        print("♣ Test files generated successfully.")
    except subprocess.CalledProcessError as e:
        print(f"♣ Failed to generate test files: {e}")
        sys.exit(1)

def run_tests():
    """Run all tests using the test runner."""
    print("\n♣ Running all tests...")
    try:
        execute_tests()
    except Exception as e:
        print(f"♣ Test execution failed: {str(e)}")
        sys.exit(1)

def main():
    """Main function to orchestrate the package management and testing."""
    print("♣ Starting overall test process...")
    print("="*60)
    
    # Check and install prerequisites
    check_and_install_prerequisites()
    
    # Build and install
    create_package()
    uninstall_previous_version()
    install_package_local()
    
    # Setup and test
    check_configuration()
    run_test_file_generator()
    run_tests()
    
    print("\n♣ Overall test process completed successfully!")

if __name__ == "__main__":
    main()
