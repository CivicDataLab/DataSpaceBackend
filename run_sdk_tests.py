#!/usr/bin/env python
"""Script to run SDK tests in the current Python environment."""

import subprocess
import sys


def check_dependencies() -> bool:
    """Check if required dependencies are installed."""
    try:
        import mypy  # type: ignore
        import pytest  # type: ignore

        return True
    except ImportError as e:
        print(f"\n❌ Missing dependency: {e.name}")
        print("\nPlease install dev dependencies:")
        print('   pip install -e ".[dev]"')
        return False


def has_coverage() -> bool:
    """Check if pytest-cov is installed."""
    try:
        import pytest_cov  # type: ignore

        return True
    except ImportError:
        return False


def run_command(description: str, command: list[str]) -> None:
    """Run a command and handle errors."""
    print(f"\n{description}")
    print("-" * 60)

    try:
        result = subprocess.run(command, check=True, capture_output=False, text=True)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error: {description} failed")
        sys.exit(1)
    except FileNotFoundError:
        print(f"\n❌ Error: Command not found. Please install dev dependencies:")
        print('   pip install -e ".[dev]"')
        sys.exit(1)


def main() -> None:
    """Run all SDK tests."""
    print("=" * 60)
    print("Running DataSpace SDK Tests")
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")
    print("=" * 60)

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Run type checking
    run_command(
        "1. Running mypy type checking...",
        [sys.executable, "-m", "mypy", "dataspace_sdk/", "--ignore-missing-imports"],
    )

    # Run SDK-specific tests (without Django)
    test_files = [
        "tests/test_auth.py",
        "tests/test_base.py",
        "tests/test_client.py",
        "tests/test_datasets.py",
        "tests/test_aimodels.py",
        "tests/test_usecases.py",
        "tests/test_exceptions.py",
    ]

    # Build pytest command
    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        *test_files,
        "-v",
        "-p",
        "no:django",  # Disable Django plugin for SDK tests
        "-o",
        "addopts=",  # Override addopts from pytest.ini to remove --nomigrations
        "--override-ini=django_find_project=false",  # Disable Django project finding
        "--noconftest",  # Don't load any conftest.py files
    ]

    pytest_cmd.extend(["--cov=dataspace_sdk", "--cov-report=term-missing"])

    run_command("2. Running SDK unit tests...", pytest_cmd)

    print("\n" + "=" * 60)
    print("✅ All SDK tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
