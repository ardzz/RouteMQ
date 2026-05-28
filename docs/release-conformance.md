# Release Conformance

RouteMQ uses tracked repository evidence for release conformance and separates file-verifiable state
from hosted GitHub or external service checks.

## File-verifiable controls

| Control | Evidence |
|---|---|
| SemVer tagging | `pyproject.toml` uses Commitizen with `tag_format = "v$version"`; `github-release.yml` validates `vMAJOR.MINOR.PATCH` tags. |
| Build provenance | CI uses GitHub Artifact Attestations for built distributions; the release workflow also invokes the SLSA generic generator. |
| SBOM | Release workflows generate a CycloneDX `sbom.json`. |
| SBOM signing | Release workflows sign `sbom.json` with Sigstore. |
| Release assets | GitHub Releases attach built distributions, `sbom.json`, and `sbom.json.sigstore.json`. |
| Scorecard workflow | `.github/workflows/scorecard.yml` runs OpenSSF Scorecard. |

## External checks

These checks require hosted results and cannot be proven from repository files alone:

- successful SLSA provenance or GitHub Artifact Attestation verification for a specific release artifact;
- current OpenSSF Scorecard score and justified exceptions;
- GitHub branch protection/rulesets;
- OpenSSF Best Practices BadgeApp project status;
- secret scanning or GitGuardian repository setting state.

## Release verification checklist

After publishing a release, verify:

1. GitHub Release exists for the tag.
2. Wheel and source distribution are attached.
3. `sbom.json` and `sbom.json.sigstore.json` are attached.
4. Artifact attestation verification succeeds for built distributions.
5. Scorecard run for the release commit is visible and reviewed.
6. `CHANGELOG.md` contains release notes for the tag.
