# DataSpace SDK Development Guide

This guide covers development, testing, and publishing of the DataSpace Python SDK.

## Project Structure

```
    DataExBackend/
    ├── dataspace_sdk/           # Main SDK package
    │   ├── __init__.py         # Package initialization and exports
    │   ├── auth.py             # Authentication client
    │   ├── base.py             # Base API client
    │   ├── client.py           # Main DataSpaceClient
    │   ├── exceptions.py       # Custom exceptions
    │   └── resources/          # Resource-specific clients
    │       ├── __init__.py
    │       ├── datasets.py     # Dataset operations
    │       ├── aimodels.py     # AI Model operations
    │       └── usecases.py     # UseCase operations
    ├── examples/               # Usage examples
    │   ├── basic_usage.py
    │   ├── organization_resources.py
    │   ├── advanced_search.py
    │   └── error_handling.py
    ├── tests/                  # Unit tests (to be created)
    ├── setup.py               # Package setup configuration
    ├── pyproject.toml         # Modern Python packaging config
    ├── MANIFEST.in            # Files to include in distribution
    ├── README_SDK.md          # SDK documentation
    └── SDK_DEVELOPMENT.md     # This file
```

## Development Setup

### 1. Install in Development Mode

```bash
cd DataExBackend
pip install -e ".[dev]"
```

This installs the SDK in editable mode with development dependencies.

### 2. Verify Installation

```python
python -c "from dataspace_sdk import DataSpaceClient; print('SDK installed successfully')"
```

## Testing

### Manual Testing

1. Update the base URL in examples to point to your DataSpace instance
2. Get a valid Keycloak token
3. Run the examples:

```bash
# Basic usage
python examples/basic_usage.py

# Organization resources
python examples/organization_resources.py

# Advanced search
python examples/advanced_search.py

# Error handling
python examples/error_handling.py
```

### Interactive Testing

```python
from dataspace_sdk import DataSpaceClient

# Initialize
client = DataSpaceClient(base_url="http://localhost:8000")

# Login
client.login(keycloak_token="your_token")

# Test operations
datasets = client.datasets.search(query="test")
print(datasets)
```

### Unit Tests (To Be Implemented)

Create tests in `tests/` directory:

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=dataspace_sdk --cov-report=html
```

## Code Quality

### Formatting

```bash
# Format code with black
black dataspace_sdk/ examples/

# Check formatting
black --check dataspace_sdk/ examples/
```

### Linting

```bash
# Lint with flake8
flake8 dataspace_sdk/ examples/

# Type checking with mypy
mypy dataspace_sdk/
```

## Building the Package

### 1. Update Version

Update version in:

- `setup.py`
- `pyproject.toml`
- `dataspace_sdk/__init__.py`

### 2. Build Distribution

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# This creates:
# - dist/dataspace_sdk-0.1.0.tar.gz (source distribution)
# - dist/dataspace_sdk-0.1.0-py3-none-any.whl (wheel)
```

### 3. Check Distribution

```bash
# Check package
twine check dist/*

# Test installation from local build
pip install dist/dataspace_sdk-0.1.0-py3-none-any.whl
```

## Publishing

### Test PyPI (Recommended First)

```bash
# Upload to Test PyPI
twine upload --repository testpypi dist/*

# Install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ dataspace-sdk
```

### Production PyPI

```bash
# Upload to PyPI
twine upload dist/*

# Install from PyPI
pip install dataspace-sdk
```

### PyPI Credentials

Create `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-your-api-token

[testpypi]
username = __token__
password = pypi-your-test-api-token
```

## Version Management

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality
- **PATCH** version for backwards-compatible bug fixes

Example: `0.1.0` → `0.2.0` (new features) → `1.0.0` (stable release)

## Release Checklist

- [ ] Update version numbers
- [ ] Update CHANGELOG.md (if exists)
- [ ] Run all tests
- [ ] Check code formatting and linting
- [ ] Build distribution packages
- [ ] Test installation from built package
- [ ] Upload to Test PyPI and verify
- [ ] Upload to Production PyPI
- [ ] Create Git tag: `git tag -a v0.1.0 -m "Release v0.1.0"`
- [ ] Push tag: `git push origin v0.1.0`
- [ ] Create GitHub release with release notes

## Adding New Features

### Adding a New Resource Client

1. Create new file in `dataspace_sdk/resources/`:

    ```python
    # dataspace_sdk/resources/newresource.py
    from dataspace_sdk.base import BaseAPIClient

    class NewResourceClient(BaseAPIClient):
        def search(self, query=None, **kwargs):
            # Implementation
            pass
    ```

2. Update `dataspace_sdk/resources/__init__.py`:

    ```python
    from dataspace_sdk.resources.newresource import NewResourceClient

    __all__ = [..., "NewResourceClient"]
    ```

3. Update `dataspace_sdk/client.py`:

    ```python
    from dataspace_sdk.resources.newresource import NewResourceClient

    class DataSpaceClient:
        def __init__(self, base_url: str):
            # ...
            self.newresource = NewResourceClient(self.base_url, self._auth)
    ```

4. Update documentation

### Adding New Methods

1. Add method to appropriate client class
2. Add docstring with parameters and return type
3. Add example in `README_SDK.md`
4. Create example file if needed

## Troubleshooting

### Import Errors

```bash
# Reinstall in development mode
pip uninstall dataspace-sdk
pip install -e .
```

### API Connection Issues

- Verify base URL is correct
- Check if API is running
- Verify network connectivity
- Check authentication token validity

### Build Issues

```bash
# Clean build artifacts
rm -rf build/ dist/ *.egg-info

# Rebuild
python -m build
```

## Best Practices

1. **Error Handling**: Always use custom exceptions
2. **Documentation**: Add docstrings to all public methods
3. **Type Hints**: Use type hints for better IDE support
4. **Backwards Compatibility**: Don't break existing APIs
5. **Testing**: Test all new features
6. **Examples**: Provide examples for new features

## Resources

- [Python Packaging Guide](https://packaging.python.org/)
- [Semantic Versioning](https://semver.org/)
- [Requests Documentation](https://requests.readthedocs.io/)
- [Type Hints PEP 484](https://www.python.org/dev/peps/pep-0484/)

## Support

For issues and questions:

- GitHub Issues: <https://github.com/CivicDataLab/DataSpace/issues>
- Email: <tech@civicdatalab.in>
