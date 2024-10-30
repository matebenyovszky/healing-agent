import os
import sys
import subprocess
import requests
import shutil
from pathlib import Path

def get_version_from_toml():
    """Get version from pyproject.toml file."""
    try:
        with open("pyproject.toml", "r") as f:
            lines = f.readlines()
            for line in lines:
                if line.strip().startswith("version = "):
                    # Extract version from line like 'version = "0.1.2"'
                    version = line.split("=")[1].strip().strip('"').strip("'")
                    return version
        raise Exception("Version not found in pyproject.toml")
    except Exception as e:
        print(f"♣ Error reading version from pyproject.toml: {str(e)}")
        sys.exit(1)

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
        'requests',
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

def build_package():
    """Build the package using the build module."""
    print("♣ Building package...")
    try:
        # Clean previous builds
        dist_dir = Path('dist')
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        
        # Build the package using build module (which will use hatchling)
        subprocess.check_call([sys.executable, "-m", "build"])
        
        # Get the built package files
        dist_files = list(dist_dir.glob('*'))
        if not dist_files:
            raise Exception("No package files were created")
        
        print("♣ Package built successfully")
        return dist_files
        
    except Exception as e:
        print(f"♣ Failed to build package: {str(e)}")
        sys.exit(1)

def create_github_release_and_upload_assets(version):
    """Create a GitHub release and upload all assets."""
    # Check for GitHub token
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set.")
        sys.exit(1)

    repo = "matebenyovszky/healing-agent"
    url = f"https://api.github.com/repos/{repo}/releases"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    data = {
        "tag_name": f"v{version}",
        "name": f"v{version}",
        "body": f"Pre-release version {version}",
        "draft": False,
        "prerelease": True
    }

    try:
        # Create the release
        print("♣ Creating GitHub release...")
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        release = response.json()
        upload_url = release['upload_url'].replace("{?name,label}", "")
        print("♣ GitHub release created successfully")

        # Build the package using hatchling
        asset_files = build_package()

        # Upload each asset
        for asset_path in asset_files:
            asset_name = asset_path.name
            print(f"♣ Uploading asset: {asset_name}")
            
            headers.update({"Content-Type": "application/octet-stream"})
            with open(asset_path, 'rb') as asset_file:
                response = requests.post(
                    f"{upload_url}?name={asset_name}",
                    headers=headers,
                    data=asset_file
                )
                response.raise_for_status()
                print(f"♣ Successfully uploaded {asset_name}")

        print("\n♣ Package release completed successfully!")
        print(f"♣ Release URL: https://github.com/{repo}/releases/tag/v{version}")
        print(f"♣ Install with: pip install git+https://github.com/{repo}@v{version}")

    except requests.exceptions.RequestException as e:
        print(f"♣ GitHub API error: {str(e)}")
        if hasattr(e, 'response'):
            print(f"♣ Response: {e.response.content}")
        sys.exit(1)
    except Exception as e:
        print(f"♣ Error: {str(e)}")
        sys.exit(1)

def main():
    """Main function to handle the release process."""
    # Get version from pyproject.toml
    version = get_version_from_toml()
    
    print(f"♣ Starting GitHub package release process for version {version}")
    print("="*60)
    
    # Check and install prerequisites
    check_and_install_prerequisites()
    
    # Create release and upload assets
    create_github_release_and_upload_assets(version)

if __name__ == "__main__":
    main() 