import argparse
import importlib.util
import os
import sys
import subprocess
import requests
import shutil
from pathlib import Path

def get_version_from_toml(project_root):
    """Get version from pyproject.toml file."""
    try:
        with open(project_root / "pyproject.toml", "r", encoding="utf-8") as f:
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

def check_prerequisites():
    """Fail safely instead of changing the release environment."""
    required_packages = ["requests", "build", "hatchling", "twine", "pytest"]
    print("♣ Checking prerequisites...")
    missing = [
        package
        for package in required_packages
        if importlib.util.find_spec(package) is None
    ]
    if missing:
        raise SystemExit(
            "Missing release dependencies: "
            + ", ".join(missing)
            + '. Install them with: pip install -e ".[dev]"'
        )

def build_package(project_root):
    """Build the package using the build module."""
    print("♣ Building package...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pytest"], cwd=project_root
        )

        # Clean previous builds
        dist_dir = project_root / "dist"
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        
        # Build the package using build module (which will use hatchling)
        subprocess.check_call(
            [sys.executable, "-m", "build"], cwd=project_root
        )
        
        # Get the built package files
        dist_files = sorted(
            list(dist_dir.glob("*.whl")) + list(dist_dir.glob("*.tar.gz"))
        )
        if not dist_files:
            raise Exception("No package files were created")

        subprocess.check_call(
            [sys.executable, "-m", "twine", "check", *map(str, dist_files)],
            cwd=project_root,
        )
        
        print("♣ Package built successfully")
        return dist_files
        
    except Exception as e:
        print(f"♣ Failed to build package: {str(e)}")
        sys.exit(1)

def create_github_release_and_upload_assets(version, asset_files):
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
        "draft": True,
        "prerelease": True
    }

    try:
        tag_response = requests.get(
            f"https://api.github.com/repos/{repo}/git/ref/tags/v{version}",
            headers=headers,
            timeout=30,
        )
        tag_response.raise_for_status()

        # Create the release
        print("♣ Creating draft GitHub prerelease...")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        release = response.json()
        upload_url = release['upload_url'].replace("{?name,label}", "")
        print("♣ GitHub release created successfully")

        # Upload each asset
        for asset_path in asset_files:
            asset_name = asset_path.name
            print(f"♣ Uploading asset: {asset_name}")
            
            headers.update({"Content-Type": "application/octet-stream"})
            with open(asset_path, 'rb') as asset_file:
                response = requests.post(
                    f"{upload_url}?name={asset_name}",
                    headers=headers,
                    data=asset_file,
                    timeout=120,
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
    parser = argparse.ArgumentParser(
        description="Build release artifacts and optionally create a draft GitHub prerelease."
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Create the draft prerelease and upload artifacts after checks pass.",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]

    # Get version from pyproject.toml
    version = get_version_from_toml(project_root)
    
    print(f"♣ Starting GitHub package release process for version {version}")
    print("="*60)
    
    check_prerequisites()
    asset_files = build_package(project_root)

    if not args.publish:
        print("♣ Checks passed; no GitHub changes made. Add --publish explicitly.")
        return

    create_github_release_and_upload_assets(version, asset_files)

if __name__ == "__main__":
    main()
