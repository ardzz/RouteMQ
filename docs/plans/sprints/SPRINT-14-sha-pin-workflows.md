# SPRINT-14 — SHA-Pin All GitHub Actions

**Generated:** 2026-05-27
**Status:** PLAN
**Priority:** MEDIUM — supply-chain hardening (Scorecard "Pinned-Dependencies" check)
**Depends on:** SPRINT-13 (Scorecard workflow must exist so it gets pinned too)

## Goal

Pin every `uses:` reference across `.github/workflows/*.yml` to a full 40-character commit SHA with a trailing `# vX.Y.Z` comment. Add Dependabot config for the `github-actions` ecosystem so SHAs stay current without manual maintenance.

## Why

OpenSSF Scorecard's `Pinned-Dependencies` check requires SHA pinning, not tag references. Tag refs are mutable; an attacker who compromises a maintainer can re-point a tag at malicious code. SHA refs are immutable and verifiable.

Most workflows in this repo already use SHA pins (verified during Sprint-11 research), but stragglers may exist. Sprint 14 makes the pinning exhaustive and enforces it via Dependabot updates.

## Tool Selection (from sprint planning research)

**`pinact` by suzuki-shunsuke** — `v4.0.0` released 2026-05-25
- Purpose-built for GitHub Actions and reusable workflows
- Preserves `# vX.Y.Z` version comments
- Supports `--verify-comment` to check that comments match SHAs
- Active maintenance (released 2 days ago at time of research)

Install + run:
```bash
go install github.com/suzuki-shunsuke/pinact@v4.0.0
PINACT_GITHUB_TOKEN="$(gh auth token)" pinact run --branch-to-tag '^main$' --branch-to-tag '^master$'
```

The `--branch-to-tag` flags convert any `@main` or `@master` references to the current SHA at that branch. Without those flags, pinact leaves branch refs alone.

## Changes

### 1. Run pinact in dry-run, review diff

```bash
# install pinact (Go must be available; if not, brew or apt)
go install github.com/suzuki-shunsuke/pinact@v4.0.0

# dry-run to see what would change
PINACT_GITHUB_TOKEN="$(gh auth token)" pinact run --verify-comment

# Apply for real
PINACT_GITHUB_TOKEN="$(gh auth token)" pinact run --branch-to-tag '^main$' --branch-to-tag '^master$'
git diff -- .github/workflows .github/actions
```

If Go is not installed, fallback approach:
```bash
# Use the prebuilt binary from GitHub release
curl -L https://github.com/suzuki-shunsuke/pinact/releases/download/v4.0.0/pinact_linux_amd64.tar.gz | tar xz
./pinact run --branch-to-tag '^main$' --branch-to-tag '^master$'
```

### 2. `.github/dependabot.yml` — append github-actions ecosystem

Current file is 335 bytes (small). Read it first; preserve existing `pip` / `npm` entries. Append:

```yaml
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Asia/Jakarta"
    open-pull-requests-limit: 5
    commit-message:
      prefix: "ci"
      include: "scope"
    labels:
      - "dependencies"
      - "github-actions"
```

The `timezone: Asia/Jakarta` matches the repo's standard timezone (per AGENTS.md).

## Verification

```bash
# Verify no tag-only refs remain
grep -rE "uses:\s+[^@]+@v[0-9]" .github/workflows .github/actions || echo "All pinned"

# Verify YAML is still valid
for f in .github/workflows/*.yml; do
  uv run python -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK: $f"
done

# Lint
uv run pre-commit run check-yaml --all-files
uv run pre-commit run check-yaml --all-files
```

Post-merge:
- Scorecard's next run (within 1 week or on next master push) should show `Pinned-Dependencies` at 10/10
- Dependabot should open its first `github-actions` PR within a week

## Risks

- **Risk:** pinact pins to a SHA that's NEWER than the tag comment, breaking compatibility. **Mitigation:** review diff carefully; reject moves that change major versions.
- **Risk:** Reusable workflow refs (`uses: org/repo/.github/workflows/X.yml@ref`) pinned to SHA may break if upstream renames files. **Mitigation:** pinact handles this correctly; verify post-pin runs.

## Out of Scope

- Adding new workflows (Sprint 13's concern: Scorecard already done)
- Modifying release.yml logic (Sprint 12 fixed it)
- Best Practices badge (Sprint 15)

## Audit Findings

- Total `uses:` references audited in `.github/workflows/*.yml`: 30
- SHA-pinned references with trailing version comments: 29 / 30
- Documented exception: 1 / 30 — `slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.1.0` in `.github/workflows/release.yml` remains tag-pinned intentionally. SLSA's generator documentation requires referencing builders and generators by tag for provenance attestation support: <https://github.com/slsa-framework/slsa-github-generator#referencing-slsa-builders-and-generators>.
- Tag-only audit result: no unexpected tag-only refs; the only match is the SLSA reusable-workflow exception above.
- Pinact verification: attempted with `pinact run --verify-comment --check`; completed cleanly with no drift reported.
