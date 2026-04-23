# Contributing to DataSpace Backend

Thank you for your interest in contributing to DataSpace Backend! We welcome contributions from the community and are pleased to have you join us.

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the existing issues to avoid duplicates. When you are creating a bug report, please include as many details as possible:

- Use a clear and descriptive title
- Describe the exact steps to reproduce the problem
- Provide specific examples to demonstrate the steps
- Describe the behavior you observed and what behavior you expected
- Include screenshots if applicable
- Include your environment details (OS, Python version, etc.)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

- Use a clear and descriptive title
- Provide a detailed description of the suggested enhancement
- Explain why this enhancement would be useful
- List some other applications where this enhancement exists, if applicable

### Pull Requests

1. Fork the repository
2. Create a feature branch from `main`: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests for your changes
5. Ensure all tests pass: `python manage.py test`
6. Run code quality checks: `black .`, `isort .`, `flake8`
7. Commit your changes: `git commit -m 'Add amazing feature'`
8. Push to the branch: `git push origin feature/amazing-feature`
9. Open a Pull Request

## Development Setup

### Prerequisites

- Python 3.8+
- PostgreSQL
- Redis
- Elasticsearch
- Keycloak server

### Local Development

1. Clone the repository:

   ```bash
   git clone https://github.com/CivicDataLab/DataSpaceBackend.git
   cd DataSpaceBackend
   ```

2. Create a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. Run migrations:

   ```bash
   python manage.py migrate
   python manage.py init_roles
   ```

6. Start the development server:

   ```bash
   python manage.py runserver
   ```

### Running Tests

```bash
# Run all tests
python manage.py test

# Run specific test file
python manage.py test tests.test_specific_module

# Run with coverage
coverage run --source='.' manage.py test
coverage report
```

### Code Style

We use several tools to maintain code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking

Run these before committing:

```bash
black .
isort .
flake8
mypy .
```

### Pre-commit Hooks

We use pre-commit hooks to ensure code quality. Install them:

```bash
pre-commit install
```

## Project Structure

- `api/`: Main API application with models, views, and GraphQL schema
- `authorization/`: Authentication and authorization components
- `DataSpace/`: Project settings and configuration
- `search/`: Search functionality and Elasticsearch integration
- `docs/`: Documentation files
- `tests/`: Test files

## API Documentation

- GraphQL Playground: `/graphql/`
- Swagger UI: `/swagger/`
- ReDoc: `/redoc/`

## Database Migrations

When making model changes:

1. Create migrations: `python manage.py makemigrations`
2. Apply migrations: `python manage.py migrate`
3. Include migration files in your PR

## Security

If you discover a security vulnerability, please email `tech@civicdatalab.in` instead of opening a public issue.

## Questions?

Feel free to open an issue for questions or join our [GitHub Discussions](https://github.com/CivicDataLab/DataSpaceBackend/discussions).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
