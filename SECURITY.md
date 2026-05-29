# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately so maintainers can assess and coordinate a fix before details are public.

1. **Primary channel:** use the GitHub Security Advisories private reporting form: <https://github.com/ardzz/RouteMQ/security/advisories/new>.
2. **Email fallback:** if the advisory form is unavailable, email the maintainer at <rekyardhana029@gmail.com>.
3. Include the affected RouteMQ version or commit, a clear description, reproduction steps or proof-of-concept details when safe to share, and any suggested mitigations.
4. Do **not** open a public GitHub issue for an undisclosed vulnerability.

Maintainers aim to acknowledge valid reports within 7 days. Public disclosure is coordinated with the reporter and uses a 90-day timeline by default, unless active exploitation or ecosystem risk requires a different schedule.

## Supported versions

The following versions of RouteMQ are currently supported with security updates:

| Version | Supported          | Notes                                      |
| ------- | ------------------ | ------------------------------------------ |
| 0.21.x  | :white_check_mark: | Current supported minor release            |
| 0.20.x  | :white_check_mark: | Security fixes for the previous minor      |
| < 0.20  | :x:                | No longer supported                        |

## Security update policy

- **Critical vulnerabilities:** maintainers target a patch release or documented mitigation within 14 days after validation.
- **High-severity vulnerabilities:** fixes are targeted for the next minor release or an earlier patch when risk warrants it.
- **Medium- and low-severity vulnerabilities:** fixes are normally bundled into the next minor release.
- Security releases are documented in the changelog and, when appropriate, in GitHub Security Advisories.

## Secure development practices

RouteMQ uses the following safeguards to reduce security and supply-chain risk:

- Static analysis and formatting gates: `ruff`, `ruff format --check`, `mypy`, and Bandit where configured in CI.
- Dependency scanning: Dependabot and `pip-audit`.
- Secrets scanning: use GitHub secret scanning or GitGuardian at the repository or organization level.
- Release transparency: CycloneDX SBOM generation, Sigstore signing, and GitHub Release asset publishing.
- Build provenance: SLSA provenance through GitHub artifact attestation workflows.
- Test quality: CI enforces the coverage floor configured in `pyproject.toml`.
- Repository health monitoring: OpenSSF Scorecard.

Security-sensitive changes should include tests or documented manual verification. Contributors should avoid suppressing type, lint, or security findings unless the reason is narrow and documented in the relevant review.

## Threat model summary

- **Trust boundaries:** MQTT topics and payloads are untrusted input. RouteMQ compiles route patterns to regular expressions and extracts route parameters from matched topics.
- **Considered vulnerabilities:** payload injection into application handlers, queue denial-of-service through unbounded or expensive jobs, unsafe dependency or build supply-chain changes, accidental secret exposure, and unsafe Redis/MySQL/MQTT configuration.
- **Out of scope:** application-level authentication and authorization are the consumer application's responsibility. RouteMQ users must configure MQTT broker access controls, credentials, network exposure, and any app-specific authorization policy.

When running with Docker, review `docker-compose.yml`, `.env.docker`, exposed ports, and default credentials before deploying beyond local development.

## Disclosure history

No public advisories at this time.
