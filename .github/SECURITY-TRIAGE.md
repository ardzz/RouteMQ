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

## Dependabot Grouping

`.github/dependabot.yml` groups patch and minor updates to cut weekly PR volume. Dependabot reads the file from the
default branch, so a group change takes effect from the first run after it lands there. Grouping changes only how
updates are bundled into PRs: schedules, `open-pull-requests-limit`, commit prefixes, labels, directories, Dependabot
alerts, and CI gates stay as configured.

| Entry | Group | `applies-to` | `dependency-type` | `update-types` | `exclude-patterns` |
|---|---|---|---|---|---|
| `github-actions` | `actions-patch-minor` | `version-updates` | any | `patch`, `minor` | none |
| `uv` | `python-dev-patch-minor` | `version-updates` | `development` | `patch`, `minor` | none |
| `uv` | `python-runtime-patch-minor` | `version-updates` | `production` | `patch`, `minor` | `aiomysql`, `asyncpg` |
| `uv` | `python-dev-security` | `security-updates` | `development` | `patch`, `minor` | none |
| `uv` | `python-runtime-security` | `security-updates` | `production` | `patch`, `minor` | `aiomysql`, `asyncpg` |
| `docker` | none | n/a | n/a | n/a | n/a |

Every group matches `patterns: ["*"]`.

- Version and security updates never share a PR. Each group sets `applies-to`, so a version-update group never picks
  up a security fix and a security group never picks up a routine bump. Security update PRs are raised from
  Dependabot alerts, not on the weekly schedule.
- Updates that match no group open as individual PRs:
  - Major updates in every ecosystem, including security fixes that need a major version bump. No declared group
    rule includes them, and no `ignore` rule hides them. dependabot-core can still mark a group's dependencies as
    handled for a run, so whether a major left out by `update-types` gets its own PR depends on existing or failed
    group PRs and on the hosted experiment `individual_prs_for_semver_excluded_dependencies`
    ([`dependency_snapshot.rb`][core-group-handled]). That individual PR is not guaranteed in every hosted run;
    confirm it after this configuration is active on the default branch.
  - `aiomysql` and `asyncpg`. They are pre-1.0, runtime-critical database drivers (MySQL and PostgreSQL), and
    Dependabot assumes every `x.y.z` version is `major.minor.patch`, so a `0.x` to `0.y` release counts as a minor
    update ([groups `update-types`][dependabot-update-types]). `exclude-patterns` only keeps them out of the runtime
    groups; it is not an `ignore` rule, so their version updates and security updates still arrive, one PR per
    driver.
  - GitHub Actions security updates. The `github-actions` entry defines no `security-updates` group.
  - Every Docker update. The `docker` entry has no groups, so base-image and interpreter changes, such as the
    scaffold template moving off `python:3.12-slim`, stay standalone.
- `uv` dependency types come from dependabot-core, not from this repository. GitHub's
  [`groups.dependency-type` reference][dependabot-groups-dependency-type] lists `bundler`, `composer`, `mix`, `maven`,
  `npm`, and `pip`, but not `uv`. In dependabot-core, group matching calls the generic `production?` check
  ([`dependency_group.rb`][core-group-type]), which flattens each requirement's `groups`
  ([`dependency.rb`][core-production]) and, for `uv`, treats a dependency as production only when that list is
  empty or contains `default`, `install_requires`, or `dependencies` ([`uv.rb`][core-uv-check]). The `uv` parser
  leaves `groups` empty for `[project].dependencies` and `[project.optional-dependencies]` entries and sets it to
  the group name for `[dependency-groups]` entries ([`parser.py`][core-uv-parser],
  [`pyproject_files_parser.rb`][core-uv-groups]). Duplicate names are merged by concatenating their requirements
  ([`dependency_set.rb`][core-dependency-set]). Packages found only in `uv.lock` are added with no requirements,
  and the subdependency check reports those as production ([`file_parser.rb`][core-uv-lock],
  [`dependency.rb`][core-production]). Applied to this repository's `pyproject.toml`, that code yields:
  - `production`: `[project].dependencies` (including `aiomysql`), packages listed only in
    `[project.optional-dependencies]` (`redis`, `asyncpg`, `prometheus-client`, `clickhouse-connect`), and transitive
    packages that appear only in `uv.lock`.
  - `development`: everything in `[dependency-groups].dev`. That includes `questionary`, `rich`, `rich-pyfiglet`,
    and `jinja2`, which are also runtime requirements of the `cli` extra, so their bumps would arrive in
    `python-dev-patch-minor` or `python-dev-security`.
  - This split is read from source, not observed from a Dependabot run. Check the first grouped `uv` PRs against it.
- `open-pull-requests-limit: 5` is set on each `updates` entry and counts only that entry's open version-update PRs.
  It is not a repository-wide cap: `github-actions`, `uv`, and `docker` can each hold five open PRs, and a grouped PR
  counts as one. Security update PRs do not count toward it; GitHub caps them separately at 10 open PRs.
- Grouping is not auto-merge. A grouped PR is reviewed and merged by hand after the CI gates pass, like an individual
  PR.
- Green PR CI is not evidence for the paths below. Collect that evidence separately before merging a grouped PR that
  touches them:
  - Release path: `release.yml`, `publish.yml`, `publish-test.yml`, and `github-release.yml` run on branch pushes,
    `v*` tags, or manual dispatch, never on pull requests. Action bumps in those workflows are not exercised by PR CI.
  - PostgreSQL: CI integration tests start Redis, MySQL, and MQTT containers only, so asyncpg never runs against a
    live PostgreSQL server.
  - Tinker: unit tests mock the Rich helpers and never start an interactive `routemq tinker` session, so IPython,
    `nest-asyncio`, and Rich bumps need a manual REPL check.

[dependabot-groups-dependency-type]: https://github.com/github/docs/blob/ae648a1d328cb15fb173e80984aac748cf4b5af2/content/code-security/reference/supply-chain-security/dependabot-options-reference.md?plain=1#L341-L343
[dependabot-update-types]: https://github.com/github/docs/blob/ae648a1d328cb15fb173e80984aac748cf4b5af2/content/code-security/reference/supply-chain-security/dependabot-options-reference.md?plain=1#L380
[core-group-type]: https://github.com/dependabot/dependabot-core/blob/95cd52ed9f6776b284441d60ddbd8d128b8648ef/common/lib/dependabot/dependency_group.rb#L125-L133
[core-production]: https://github.com/dependabot/dependabot-core/blob/95cd52ed9f6776b284441d60ddbd8d128b8648ef/common/lib/dependabot/dependency.rb#L241-L259
[core-uv-check]: https://github.com/dependabot/dependabot-core/blob/95cd52ed9f6776b284441d60ddbd8d128b8648ef/uv/lib/dependabot/uv.rb#L34-L43
[core-uv-parser]: https://github.com/dependabot/dependabot-core/blob/95cd52ed9f6776b284441d60ddbd8d128b8648ef/uv/helpers/lib/parser.py#L106-L131
[core-uv-groups]: https://github.com/dependabot/dependabot-core/blob/95cd52ed9f6776b284441d60ddbd8d128b8648ef/uv/lib/dependabot/uv/file_parser/pyproject_files_parser.rb#L114
[core-dependency-set]: https://github.com/dependabot/dependabot-core/blob/95cd52ed9f6776b284441d60ddbd8d128b8648ef/common/lib/dependabot/file_parsers/base/dependency_set.rb#L146-L148
[core-uv-lock]: https://github.com/dependabot/dependabot-core/blob/95cd52ed9f6776b284441d60ddbd8d128b8648ef/uv/lib/dependabot/uv/file_parser.rb#L198-L208
[core-group-handled]: https://github.com/dependabot/dependabot-core/blob/95cd52ed9f6776b284441d60ddbd8d128b8648ef/updater/lib/dependabot/dependency_snapshot.rb#L215-L266

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
