# ADR-0009: Supply-Chain Provenance and Release Transparency

**Status:** Accepted
**Date:** 2026-05-29
**Sprint:** Sprints 02, 03, 13, 14, and 18

## Context

Industrial-grade open-source frameworks need release artifacts that users can verify. RouteMQ publishes
Python distributions and GitHub Release assets, so consumers need more than a tag and a changelog: they
need build provenance, dependency transparency, and a repeatable release path that downstream automation
can observe.

The release pipeline also had to account for GitHub's token behavior. Workflows triggered by `GITHUB_TOKEN`
pushes are suppressed to prevent infinite loops, which means tag creation by the release job cannot rely on
that token when downstream release workflows must run.

## Decision

Use standard supply-chain evidence in the existing GitHub release workflows:

1. **SLSA Build L3 provenance** is produced through `slsa-framework/slsa-github-generator` from
   `.github/workflows/release.yml`.
2. **CycloneDX SBOM** assets are generated during release and attached to GitHub Releases.
3. **Sigstore signing** signs the SBOM artifacts from `release.yml` and `github-release.yml` so release
   assets carry verifiable provenance and dependency transparency.
4. **OpenSSF Scorecard** runs weekly from `.github/workflows/scorecard.yml`, with the live badge exposed in
   README.
5. **Tag pushes use a fine-grained `RELEASE_TOKEN` personal access token** so downstream workflows such as
   `github-release.yml` fire after the release job creates a tag. This avoids the GitHub suppression applied
   to `GITHUB_TOKEN` workflow-triggered pushes.

## Consequences

### Positive

- Every release has provenance, SBOM, and signed SBOM artifacts.
- Consumers can verify release evidence using standard SLSA, CycloneDX, and Sigstore tooling.
- Scorecard remains visible as a live external quality signal rather than a stale embedded number.
- The release pipeline is reproducible and can trigger the downstream GitHub Release asset workflow.

### Negative

- Release automation depends on a correctly scoped `RELEASE_TOKEN` secret.
- Provenance and SBOM evidence are generated at release time, so local builds remain unauthenticated unless
  users run their own equivalent pipeline.
- Scorecard and Best Practices status still depend on hosted external systems outside the repository.

## Status

Accepted across Sprints 02, 03, 13, 14, and 18. PR #63 records the release-token fix that allowed
tag-triggered downstream workflows to run.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| No provenance | Users would have to trust release artifacts without build-chain evidence. |
| Embedded provenance format | Non-standard and harder for downstream tools to verify than SLSA and Sigstore evidence. |
| Pushgateway-style external service | Adds infrastructure and operational burden without improving the standard release artifact story. |

## Related

- `.github/workflows/release.yml`: build, provenance, SBOM, and tag automation.
- `.github/workflows/github-release.yml`: GitHub Release assets and signing.
- `.github/workflows/scorecard.yml`: weekly OpenSSF Scorecard run.
- PR #63: fine-grained `RELEASE_TOKEN` fix for downstream workflow triggering.
