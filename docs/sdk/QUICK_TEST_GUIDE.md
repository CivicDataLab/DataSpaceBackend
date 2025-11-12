# Quick Test Guide

## Setup (One Time)

```bash
# Install SDK with dev dependencies
pip install -e ".[dev]"
```

## Run Tests

```bash
# Run all SDK tests (recommended - uses current Python environment)
python run_sdk_tests.py

# Or run specific tests
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_datasets.py -v
python -m pytest tests/test_aimodels.py -v
python -m pytest tests/test_usecases.py -v
```

## Check Coverage

```bash
python -m pytest tests/ --cov=dataspace_sdk --cov-report=term-missing
```

## Type Checking

```bash
mypy dataspace_sdk/ --ignore-missing-imports
```

## CI/CD

Tests run automatically on:

- Push to `dev` or `main`
- Pull requests to `dev` or `main`

Check results in GitHub Actions tab.
