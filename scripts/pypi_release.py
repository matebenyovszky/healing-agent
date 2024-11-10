import os
import sys
import subprocess
from pathlib import Path

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
        'twine',
        'build',
        'hatchling'
    ]
    
    print("♣ Checking prerequisites...")
    for package in required_packages:
        try:
            __import__(package)
            print(f"♣ {package} is already installed")
        except ImportError:
            print(f"♣ Installing {package}...")
            install_package(package)

def build_and_upload_to_pypi(use_test_pypi=True):
    """Build and upload package to PyPI or TestPyPI."""
    # Get appropriate token from environment variable
    if use_test_pypi:
        token = os.getenv('PYPI_TEST_TOKEN')
        if not token:
            print("♣ Error: PYPI_TEST_TOKEN environment variable must be set with your TestPyPI API token")
            print("♣ Please set it using:")
            print("  export PYPI_TEST_TOKEN=your-test-api-token")
            sys.exit(1)
    else:
        token = os.getenv('PYPI_PROD_TOKEN')
        if not token:
            print("♣ Error: PYPI_PROD_TOKEN environment variable must be set with your PyPI API token")
            print("♣ Please set it using:")
            print("  export PYPI_PROD_TOKEN=your-prod-api-token")
            sys.exit(1)

    try:
        # Build the package
        print("♣ Building package...")
        subprocess.check_call([sys.executable, "-m", "build"])

        # Set repository URL based on target
        repo_url = "https://test.pypi.org/legacy/" if use_test_pypi else "https://upload.pypi.org/legacy/"
        target_name = "TestPyPI" if use_test_pypi else "PyPI"

        print(f"♣ Uploading to {target_name}...")
        dist_files = list(Path("dist").glob("*"))
        if not dist_files:
            print("♣ Error: No distribution files found in dist/")
            sys.exit(1)
            
        cmd = [
            sys.executable, "-m", "twine", "upload",
            "--repository-url", repo_url,
            *[str(f) for f in dist_files],
            "--username", "__token__",
            "--password", token,
            "--verbose"
        ]
        subprocess.check_call(cmd)
        print(f"♣ Successfully uploaded to {target_name}")
        
    except subprocess.CalledProcessError as e:
        print(f"♣ Error during build/upload process: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("♣ Starting PyPI release process")
    print("="*60)
    
    # Get target from command line argument
    use_test_pypi = True  # Default to TestPyPI
    if len(sys.argv) > 1 and sys.argv[1].lower() == "prod":
        use_test_pypi = False
    
    target = "TestPyPI" if use_test_pypi else "PyPI"
    print(f"♣ Target repository: {target}")
    
    check_and_install_prerequisites()
    build_and_upload_to_pypi(use_test_pypi)