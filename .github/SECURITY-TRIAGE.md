# Security Vulnerability Triage Process

## Scope

- Covers Bandit SAST findings, pip-audit dependency CVE findings, Dependabot alerts on `uv.lock`, and future
  scanners that report actionable vulnerability findings.
- Does not cover secret-scanning findings. Secret-scanning is handled separately through GitGuardian or
  GitHub secret-scanning.

## Dependency Sources of Truth

- `pyproject.toml` declares the allowed ranges; `uv.lock` pins the complete resolution. Do not add
  `requirements*.txt` files as a second dependency list; requirements files used for auditing are exported from
  `uv.lock` into a temporary path and never committed.
- Every repository-bound `uv sync`, `uv run`, and `uv export` in the workflows passes `--locked`. A manifest
  change without a matching `uv.lock` update fails CI instead of being re-resolved silently. `uv build` does not
  read `uv.lock`, so jobs that build without a prior `uv sync --locked` run `uv lock --check` first.
- Dependabot (`.github/dependabot.yml`) runs weekly on Monday 09:00 Asia/Jakarta:
  - `uv` at `/` updates `pyproject.toml` and `uv.lock` together. Labels: `dependencies`, `python`.
  - `docker` at `/` and `/routemq/scaffold/templates/features/docker` updates literal image references in the root
    `Dockerfile` and the scaffold Docker template. Label: `dependencies`. Dependabot does not update images selected
    through `ARG` (the root `python:${PYTHON_VERSION}-slim` base) or floating tags such as
    `ghcr.io/astral-sh/uv:latest`; bump those manually.
  - `github-actions` at `/` updates SHA-pinned workflow actions. Labels: `dependencies`, `github-actions`.
- Dependabot security update PRs are `uv.lock` changes and go through the same CI gates as any other change.

## Remediating a Vulnerable Dependency

1. Upgrade only the affected package in the lock:

   ```bash
   uv lock --upgrade-package <package>   # or <package>==<fixed-version>
   ```

   If the fixed version is outside the range declared in `pyproject.toml`, raise the bound there first, then run
   `uv lock`.
2. Confirm the lock matches the manifest and reinstall from it:

   ```bash
   uv lock --check
   uv sync --locked --all-extras --dev
   ```

3. Re-run the security gate commands below and the regular test, lint, and type-check gates. Commit
   `pyproject.toml` (when changed) and `uv.lock` together.

## Security Gate Commands

The CI `security` job runs these commands from a clean checkout. Locally, use any temporary file in place of
`$RUNNER_TEMP/runtime-requirements.txt`.

```bash
uv sync --locked --all-extras --dev
uv run --locked bandit -c pyproject.toml -r routemq app bootstrap
uv run --locked pip-audit
uv export --locked --format requirements.txt --no-dev --all-extras --no-extra dev \
  --no-emit-project --output-file "$RUNNER_TEMP/runtime-requirements.txt"
uv run --locked pip-audit --strict --disable-pip --require-hashes \
  --requirement "$RUNNER_TEMP/runtime-requirements.txt"
```

- The first `pip-audit` run audits the full installed environment: base dependencies, every extra, and the `dev`
  dependency group, including the audit tooling itself.
- The second run audits the runtime profile directly from `uv.lock`: base dependencies plus every extra except
  `dev`, without the `dev` group and without RouteMQ itself. This covers the extras users can select and the
  `uv sync --no-dev` set installed by the Docker image, at the versions pinned in `uv.lock`. Environment markers
  are evaluated for the auditing interpreter (CI: Linux, Python 3.12). `--strict` fails the run if any exported
  package cannot be audited; `--require-hashes` requires every pinned requirement to carry its lock hash.
- Do not pass `--ignore-vuln` or skip packages in CI to get a passing run; use the suppression process below.

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
  CI also accepts manual `workflow_dispatch` runs, for example `gh workflow run ci.yml --ref <branch>`.
- Failed scheduled scans open an issue automatically in a future sprint.

## Reporting

- Externally reported vulnerabilities through GitHub Security Advisories, email, or similar channels follow the
  standard GitHub coordinated-disclosure flow.
- Public `SECURITY.md`, if present, defines disclosure expectations.
