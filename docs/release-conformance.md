# Release Conformance

RouteMQ tracks release-conformance evidence in the repository and links to live hosted checks where the
result depends on GitHub or an external service.

## Evidence matrix

| Pillar | Status | Evidence | Last verified |
|---|---|---|---|
| SLSA Build L3 | Achieved | [`release.yml`](../.github/workflows/release.yml) provenance job calling `slsa-framework/slsa-github-generator` | [Latest GitHub Release](https://github.com/ardzz/RouteMQ/releases/latest) |
| OpenSSF Scorecard | Live scorecard | [`scorecard.yml`](../.github/workflows/scorecard.yml) and [README badge](https://api.scorecard.dev/projects/github.com/ardzz/RouteMQ/badge) | [Scorecard viewer](https://scorecard.dev/viewer/?uri=github.com/ardzz/RouteMQ) |
| CycloneDX SBOM | Generated + signed | [`release.yml`](../.github/workflows/release.yml) and [`github-release.yml`](../.github/workflows/github-release.yml) Sigstore signing steps | [Latest GitHub Release](https://github.com/ardzz/RouteMQ/releases/latest) |
| OpenSSF Best Practices | Sprint 15 in-progress | [README placeholder](../README.md#project-health) and local Sprint 15 plan | n/a |
| SemVer | Pre-1.0 contract | [`pyproject.toml`](../pyproject.toml) version metadata and this document's Versioning section | continuously |

## Versioning

RouteMQ follows Semantic Versioning 2.0.0. The framework is at 0.x.y during
pre-stable development; under the SemVer pre-1.0 rules, breaking changes
may land in minor bumps (0.X.0). Patch bumps (0.x.Y) remain
backwards-compatible.

Path to 1.0.0:
- Public API surface frozen for at least one minor cycle without breaking changes
- All standards-anchored sprints (01-07) closed
- Sprint 15 (OpenSSF Best Practices badge) submitted and passing
- At least one external production deployment reported and stable
- 90-day vulnerability response SLA published and met for any reported issue

The underlying architecture and release decisions are recorded in ADR-0001 through ADR-0009, including
distribution, logging, observability, pooling, benchmarking, error handling, and supply-chain provenance.
