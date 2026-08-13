import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

def check_prerequisites():
    """Fail safely instead of mutating the release environment."""
    required_packages = ["twine", "build", "hatchling", "pytest"]
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

def build_and_upload_to_pypi(use_test_pypi, project_root):
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
        # Test and build from a clean output directory.
        subprocess.check_call(
            [sys.executable, "-m", "pytest"], cwd=project_root
        )
        dist_dir = project_root / "dist"
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        print("♣ Building package...")
        subprocess.check_call(
            [sys.executable, "-m", "build"], cwd=project_root
        )

        # Set repository URL based on target
        repo_url = "https://test.pypi.org/legacy/" if use_test_pypi else "https://upload.pypi.org/legacy/"
        target_name = "TestPyPI" if use_test_pypi else "PyPI"

        print(f"♣ Uploading to {target_name}...")
        dist_files = sorted(
            list(dist_dir.glob("*.whl")) + list(dist_dir.glob("*.tar.gz"))
        )
        if not dist_files:
            print("♣ Error: No distribution files found in dist/")
            sys.exit(1)

        subprocess.check_call(
            [sys.executable, "-m", "twine", "check", *map(str, dist_files)],
            cwd=project_root,
        )
            
        cmd = [
            sys.executable, "-m", "twine", "upload",
            "--repository-url", repo_url,
            *[str(f) for f in dist_files],
            "--username", "__token__",
            "--password", token,
            "--verbose"
        ]
        subprocess.check_call(cmd, cwd=project_root)
        print(f"♣ Successfully uploaded to {target_name}")
        
    except subprocess.CalledProcessError as e:
        print(f"♣ Error during build/upload process: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test, build, check, and explicitly publish Healing Agent."
    )
    parser.add_argument(
        "target",
        choices=("test", "prod"),
        help="Use 'test' for TestPyPI or explicitly use 'prod' for PyPI.",
    )
    args = parser.parse_args()

    print("♣ Starting PyPI release process")
    print("="*60)

    use_test_pypi = args.target == "test"
    
    target = "TestPyPI" if use_test_pypi else "PyPI"
    print(f"♣ Target repository: {target}")
    
    check_prerequisites()
    build_and_upload_to_pypi(
        use_test_pypi, Path(__file__).resolve().parents[1]
    )
