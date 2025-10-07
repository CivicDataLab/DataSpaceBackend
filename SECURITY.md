# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of DataSpace Backend seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### How to Report

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:
- **Email**: tech@civicdatalab.in
- **Subject**: [SECURITY] DataSpace Backend - Brief Description

You should receive a response within 48 hours. If for some reason you do not, please follow up via email to ensure we received your original message.

### What to Include

Please include the following information in your report:

- Type of vulnerability (e.g., SQL injection, authentication bypass, privilege escalation, etc.)
- Full paths of source file(s) related to the vulnerability
- The location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### Response Process

1. **Acknowledgment**: We will acknowledge receipt of your vulnerability report within 48 hours
2. **Assessment**: Our security team will investigate and assess the vulnerability
3. **Updates**: We will keep you informed about the progress of fixing the vulnerability
4. **Resolution**: Once fixed, we will notify you and publicly disclose the vulnerability (with credit to you, if desired)

## Security Best Practices

### For Contributors

When contributing to this project, please follow these security guidelines:

#### Authentication & Authorization
- Never commit credentials, API keys, or secrets to the repository
- Use environment variables for all sensitive configuration (`.env` file)
- Implement proper permission checks for all API endpoints
- Validate Keycloak tokens on every protected endpoint
- Use role-based access control (RBAC) appropriately
- Never bypass authentication checks, even in development

#### Data Protection
- Always use parameterized queries to prevent SQL injection
- Sanitize and validate all user inputs
- Encrypt sensitive data at rest and in transit
- Never log sensitive information (passwords, tokens, PII)
- Implement proper data access controls
- Use Django's built-in security features

#### API Security
- Validate all GraphQL queries and mutations
- Implement proper rate limiting
- Use CORS policies appropriately
- Validate file uploads (type, size, content)
- Implement proper error handling without exposing sensitive details
- Use HTTPS only in production

#### Dependencies
- Regularly update dependencies to patch known vulnerabilities
- Run security audits before deploying
- Review security advisories for critical dependencies
- Pin dependency versions in requirements.txt
- Use virtual environments for isolation

#### Code Quality
- Follow Django security best practices
- Use Django's ORM to prevent SQL injection
- Implement CSRF protection for state-changing operations
- Validate and sanitize all user-generated content
- Use type hints and static analysis (mypy)
- Follow the principle of least privilege

### For Deployment

#### Environment Configuration
- Use strong, unique `SECRET_KEY` in production
- Configure Keycloak with proper security settings
- Enable HTTPS and HSTS in production
- Set `DEBUG=False` in production
- Configure proper database credentials
- Use secure session and cookie settings
- Set appropriate CORS and CSRF settings

#### Database Security
- Use strong database passwords
- Limit database user permissions
- Enable SSL/TLS for database connections
- Regular database backups
- Implement proper data retention policies
- Use connection pooling securely

#### Infrastructure
- Keep Python and system packages updated
- Use security headers (HSTS, X-Frame-Options, CSP, etc.)
- Implement rate limiting at multiple levels
- Regular security audits and penetration testing
- Monitor for suspicious activity
- Use a Web Application Firewall (WAF)

#### Monitoring & Logging
- Enable OpenTelemetry for distributed tracing
- Implement structured logging with `structlog`
- Monitor for security events and anomalies
- Set up alerts for critical security issues
- Regular log analysis
- Exclude sensitive data from logs

## Known Security Considerations

### Authentication System
- **Keycloak Integration**: All authentication is handled through Keycloak
- **Token Validation**: JWT tokens are validated on every request
- **No Development Bypass**: No fallback authentication mechanisms
- **User Synchronization**: User data synced from Keycloak using KeycloakAdmin
- **Session Management**: Follows OWASP session management guidelines

### API Security
- **GraphQL**: Implements query complexity limits and depth restrictions
- **REST API**: Rate limiting and throttling enabled
- **File Uploads**: Validated for type, size, and content
- **Data Versioning**: DVC integration for data versioning and tracking

### Data Protection
- **Encryption**: All data encrypted in transit (TLS 1.2+)
- **Database**: PostgreSQL with proper access controls
- **Search**: Elasticsearch with authentication enabled
- **Caching**: Redis with secure configuration
- **File Storage**: Secure file handling and validation

### Third-Party Services
- **Keycloak**: Ensure proper realm and client configuration
- **Elasticsearch**: Enable security features and authentication
- **Redis**: Use password protection and disable dangerous commands
- **OpenTelemetry**: Configure to exclude sensitive data
- **DVC**: Secure data versioning and storage

## Security Checklist for Pull Requests

Before submitting a PR, ensure:

- [ ] No hardcoded secrets or credentials
- [ ] All user inputs are validated and sanitized
- [ ] SQL injection prevention (use ORM or parameterized queries)
- [ ] Authentication and authorization checks are in place
- [ ] Dependencies are up to date and audited
- [ ] Error messages don't expose sensitive information
- [ ] Rate limiting is implemented where needed
- [ ] CORS and CSRF policies are properly configured
- [ ] Type hints are used and mypy checks pass
- [ ] Security-related changes are documented
- [ ] Tests include security scenarios

## Common Vulnerabilities to Avoid

### SQL Injection
```python
# ❌ Bad - Vulnerable to SQL injection
User.objects.raw(f"SELECT * FROM users WHERE username = '{username}'")

# ✅ Good - Use ORM or parameterized queries
User.objects.filter(username=username)
```

### XSS Prevention
```python
# ❌ Bad - Unescaped user input
return HttpResponse(f"<h1>Hello {user_input}</h1>")

# ✅ Good - Use Django templates or escape manually
from django.utils.html import escape
return HttpResponse(f"<h1>Hello {escape(user_input)}</h1>")
```

### Authentication Bypass
```python
# ❌ Bad - Skipping authentication
if settings.DEBUG:
    return True  # Allow access in debug mode

# ✅ Good - Always validate authentication
if not request.user.is_authenticated:
    raise PermissionDenied()
```

### Insecure Direct Object References
```python
# ❌ Bad - No authorization check
dataset = Dataset.objects.get(id=dataset_id)

# ✅ Good - Check user permissions
dataset = Dataset.objects.get(id=dataset_id)
if not user.has_perm('view_dataset', dataset):
    raise PermissionDenied()
```

## Vulnerability Disclosure Policy

When we receive a security bug report, we will:

1. Confirm the problem and determine affected versions
2. Audit code to find similar problems
3. Prepare fixes for all supported versions
4. Release new versions as soon as possible
5. Prominently announce the issue in release notes
6. Update this security policy if needed

## Security Updates

Security updates will be released as patch versions and will be clearly marked in the release notes.

Subscribe to our GitHub releases to stay informed about security updates.

## Security Testing

We recommend the following security testing practices:

### Static Analysis
```bash
# Run mypy for type checking
mypy .

# Run flake8 for code quality
flake8 .

# Run bandit for security issues
bandit -r api/ authorization/ search/
```

### Dependency Scanning
```bash
# Check for known vulnerabilities
pip-audit

# Or use safety
safety check
```

### Pre-commit Hooks
We use pre-commit hooks to enforce security checks. Install them with:
```bash
pre-commit install
```

## Compliance

This project aims to comply with:
- OWASP Top 10 security risks
- GDPR data protection requirements
- Industry-standard security practices
- Django security best practices

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Django Security Documentation](https://docs.djangoproject.com/en/stable/topics/security/)
- [GraphQL Security Best Practices](https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html)
- [Keycloak Security Documentation](https://www.keycloak.org/docs/latest/server_admin/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)

## Security Contacts

For any security-related questions or concerns, please contact:
- **Email**: tech@civicdatalab.in
- **GitHub**: [CivicDataLab/DataSpaceBackend](https://github.com/CivicDataLab/DataSpaceBackend)

## Security Incident Response

In case of a security incident:

1. **Immediate Response**: Isolate affected systems
2. **Assessment**: Determine scope and impact
3. **Containment**: Prevent further damage
4. **Eradication**: Remove the threat
5. **Recovery**: Restore normal operations
6. **Post-Incident**: Document and learn from the incident

---

Last Updated: October 2025
