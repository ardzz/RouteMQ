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

## Dead-code audit

Audit ran on 2026-05-29 with `vulture 2.16`:

```bash
vulture routemq app bootstrap --min-confidence 80
```

Findings count: 13 candidates above 80% confidence.

| Finding | Classification | Rationale |
|---|---|---|
| `bootstrap/app.py:173` unused `flags` | Accepted | Paho MQTT `on_connect` callback signature; framework must keep the broker callback shape. |
| `bootstrap/app.py:173` unused `userdata` | Accepted | Paho MQTT `on_connect` callback signature; user data may be supplied by the client library. |
| `bootstrap/app.py:186` unused `userdata` | Accepted | Paho MQTT `on_message` callback signature; unused locally but required by callback contract. |
| `bootstrap/app.py:243` unused `userdata` | Accepted | Paho MQTT `on_disconnect` callback signature; unused locally but required by callback contract. |
| `bootstrap/app.py:249` unused `frame` | Accepted | Python signal-handler signature; frame is available for debuggers but not needed for shutdown. |
| `routemq/health.py:73` unused `format` | Accepted | `BaseHTTPRequestHandler.log_message` override signature; returning suppresses noisy access logs. |
| `routemq/queue/queue_worker.py:68` unused `frame` | Accepted | Python signal-handler signature for queue-worker shutdown. |
| `routemq/router.py:87` unused `exc_tb` | Accepted | Context-manager `__exit__` protocol signature for router groups. |
| `routemq/router.py:87` unused `exc_val` | Accepted | Context-manager `__exit__` protocol signature for router groups. |
| `routemq/tinker.py:446` unused `get_ipython` import | Removed | Interactive helper imported the symbol but never used it; removing it does not affect the public tinker API. |
| `routemq/worker_manager.py:78` unused `flags` | Accepted | Paho MQTT worker `on_connect` callback signature. |
| `routemq/worker_manager.py:78` unused `userdata` | Accepted | Paho MQTT worker `on_connect` callback signature. |
| `routemq/worker_manager.py:87` unused `userdata` | Accepted | Paho MQTT worker `on_message` callback signature. |

The underlying architecture and release decisions are recorded in ADR-0001 through ADR-0009, including
distribution, logging, observability, pooling, benchmarking, error handling, and supply-chain provenance.

## Submitting the OpenSSF Best Practices badge

Submit RouteMQ to BadgeApp at <https://www.bestpractices.dev/en/projects/new>.

Use these required fields:

- Project name: `RouteMQ`
- Project URL: `https://github.com/ardzz/RouteMQ`
- License: `MIT`

BadgeApp auto-detects most GitHub-observable criteria from repository metadata and files. The operator should answer the remaining MUST, SHOULD, and SUGGESTED items manually based on the current repository state and hosted settings.

After submission returns a project ID, replace the placeholder in `README.md` with the real ID, for example:

```bash
sed -i 's|<PROJECT_ID>|12345|g' README.md
```

Then remove the surrounding `<!-- TODO(sprint-15-followup): ... -->` HTML comment block so the badge renders normally. The placeholder in `README.md` and this section remain active until the operator completes the BadgeApp submission.

Hosted security-setting follow-ups:

- Private vulnerability reporting was enabled on 2026-05-29 with `gh api`.
- Dependabot security updates could not be enabled automatically because GitHub returned `422 Vulnerability alerts must be enabled to configure automated security fixes`; the operator should enable vulnerability alerts, then enable Dependabot security updates.
