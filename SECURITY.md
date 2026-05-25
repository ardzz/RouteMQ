# Security Policy

## Supported Versions

The following versions of RouteMQ are currently supported with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.12.x  | :white_check_mark: |
| < 0.12  | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in RouteMQ, please report it responsibly:

1. **Do not open a public issue.** Instead, email the maintainers directly at the contact address listed in the repository.
2. Provide a clear description of the vulnerability, including steps to reproduce if applicable.
3. Allow reasonable time for the maintainers to assess and address the issue before any public disclosure.

## Security Considerations

- RouteMQ connects to MQTT brokers and optional backend services (Redis, MySQL). Ensure broker credentials and connection strings are stored securely (e.g., environment variables or secrets management), not committed to version control.
- When running with Docker, review `docker-compose.yml` and `.env.docker` for exposed ports and default credentials before deploying to production.
- The framework does not provide authentication or authorization out of the box; implement appropriate access controls at the MQTT broker or application layer.
