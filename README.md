# DataSpace Backend

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-5.0+-green.svg)](https://djangoproject.com/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Issues](https://img.shields.io/github/issues/CivicDataLab/DataSpaceBackend)](https://github.com/CivicDataLab/DataSpaceBackend/issues)
[![Contributors](https://img.shields.io/github/contributors/CivicDataLab/DataSpaceBackend)](https://github.com/CivicDataLab/DataSpaceBackend/graphs/contributors)

## Overview

DataSpace is a platform for sharing and managing datasets. This repository contains the backend code for the DataSpace platform, built with Django and GraphQL.

## Key Features

- **Secure Authentication**: Integration with Keycloak for robust authentication
- **Role-Based Access Control**: Fine-grained permissions based on user roles
- **GraphQL API**: Modern API with efficient data fetching
- **REST API**: Traditional REST endpoints for specific operations
- **Data Management**: Tools for dataset management and organization

## Authentication System

The backend uses Keycloak for authentication, providing a secure and scalable solution. Key aspects of the authentication system include:

- **Token-Based Authentication**: All requests require a valid Keycloak JWT token
- **Direct Validation**: Tokens are validated directly with Keycloak
- **User Synchronization**: User data is synchronized from Keycloak to the Django database
- **No Development Mode**: The system only works with real Keycloak tokens, with no fallback mechanisms

For detailed information about the Keycloak integration, see the [Keycloak Integration Documentation](docs/keycloak_integration.md).

## Getting Started

### Prerequisites

- Python 3.8+
- PostgreSQL
- Keycloak server

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/CivicDataLab/DataSpaceBackend.git
   cd DataSpaceBackend
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set up environment variables (create a `.env` file in the project root):
   ```
   DEBUG=True
   SECRET_KEY=your-secret-key
   DB_ENGINE=django.db.backends.postgresql
   DB_NAME=dataspace
   DB_USER=postgres
   DB_PASSWORD=postgres
   DB_HOST=localhost
   DB_PORT=5432
   KEYCLOAK_SERVER_URL=https://your-keycloak-server/auth
   KEYCLOAK_REALM=your-realm
   KEYCLOAK_CLIENT_ID=your-client-id
   KEYCLOAK_CLIENT_SECRET=your-client-secret
   ```

4. Run migrations:
   ```bash
   python manage.py migrate
   ```

5. Initialize roles:
   ```bash
   python manage.py init_roles
   ```

6. Start the development server:
   ```bash
   python manage.py runserver
   ```

## API Documentation

API documentation is available at the following endpoints when the server is running:

- Swagger UI: `/swagger/`
- ReDoc: `/redoc/`
- GraphQL Playground: `/graphql/`

## Directory Structure

- `api/`: Main API application with models, views, and GraphQL schema
- `authorization/`: Authentication and authorization components
- `DataSpace/`: Project settings and configuration
- `docs/`: Documentation files
- `search/`: Search functionality and Elasticsearch integration

## Contributing

1. Create a feature branch from the `main` branch
2. Make your changes
3. Submit a pull request

## License

This project is licensed under the [MIT License](LICENSE).
