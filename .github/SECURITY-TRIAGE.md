# Security Vulnerability Triage Process

## Scope

- Covers Bandit SAST findings, pip-audit dependency CVE findings, and future scanners that report
  actionable vulnerability findings.
- Does not cover secret-scanning findings. Secret-scanning is handled separately through GitGuardian or
  GitHub secret-scanning.

## Severity Classification

| Unified | Bandit | pip-audit (CVSS) | SLA to acknowledge | SLA to resolve |
|---|---|---|---|---|
| Critical | n/a | 9.0-10.0 | 1 business day | 7 calendar days |
| High | High | 7.0-8.9 | 2 business days | 14 calendar days |
| Medium | Medium | 4.0-6.9 | 5 business days | 30 calendar days |
| Low | Low | 0.1-3.9 | best-effort | best-effort |
| Info | n/a (low confidence) | n/a | n/a - TP review only | n/a |

## Triage Decision Tree

1. New finding appears in CI output.
2. Reviewer classifies the finding. The default reviewer is the PR author. Escalate to CODEOWNERS if
   ownership is unclear.
3. Use one of these outcomes:

- **TP (true positive)** - real vulnerability exploitable in this codebase's usage. Open an issue, label
  `security:tp`, attach the finding ID, and prioritize per the SLA above.
- **FP (false positive)** - finding does not apply. Examples: dev-only dependency, unreachable code path, or
  wrong tool inference. Suppress per the Suppression section below; document rationale in the PR or issue.
- **Won't fix (accepted risk)** - TP but business-justified. Requires CODEOWNER sign-off; document in
  `.github/SECURITY-EXCEPTIONS.md` created on first use; review at least quarterly.

## Suppression Mechanisms

### Bandit

- Per-line: `# nosec B<rule-id>  # <one-line rationale>`; must include rule ID and rationale.
- Per-file: `# nosec  # justified at top-of-file: <rationale>`.
- Repo-wide: `pyproject.toml [tool.bandit]` `skips` or `tests` arrays. Requires PR review and CODEOWNER
  sign-off.

### pip-audit

- Per-vulnerability ignore: `pyproject.toml [tool.pip-audit]`, if supported in the current version, or CLI flag
  `--ignore-vuln <ID>`.
- Document each ignore in a `.github/PIP_AUDIT_IGNORES.md` table with columns: ID, Package, Reason,
  Reviewer, Expires.
- Expire ignores no later than the next major dependency bump or 90 days, whichever comes sooner.

## Ownership

- First reviewer: PR author who introduced the dependency or code path.
- Escalation: CODEOWNERS for the affected module. See `.github/CODEOWNERS`.
- Security questions: use GitHub Security Advisories for private reports, or email the maintainer listed in
  `SECURITY.md` when the advisory form is unavailable.

## Re-Validation Cadence

- Suppressions and accepted-risk entries are reviewed quarterly on the first Monday of each quarter.
- A scheduled GitHub Action runs CI weekly to catch newly disclosed dependency and SAST findings in already-deployed dependencies.
- Failed scheduled scans open an issue automatically in a future sprint.

## Reporting

- Externally reported vulnerabilities through GitHub Security Advisories, email, or similar channels follow the
  standard GitHub coordinated-disclosure flow.
- Public `SECURITY.md`, if present, defines disclosure expectations.
