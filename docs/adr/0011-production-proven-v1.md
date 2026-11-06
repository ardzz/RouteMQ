# ADR-0011: Production-Proven v1 Release Evidence

**Status:** Accepted
**Date:** 2026-07-17

## Context

RouteMQ is currently v0.24.0 beta. This ADR defines the evidence RouteMQ must
produce before it can claim a production-proven v1 release. Accepting this
policy does not show that the current beta has met any release gate.

Qualification must prove one complete path: configuration, startup, MQTT
ingress, route, one job, telemetry write, shutdown, and observable evidence.
Isolated unit coverage cannot substitute for that path. Release evidence must
advance through the Evidence Ladder in this record. A lower rung cannot replace
a higher rung.

## Decision

### Stable, experimental, and internal boundary

The v1 boundary is intentionally narrow.

| Classification | Included surfaces | Contract |
|---|---|---|
| Stable | Core MQTT routing, Redis, MySQL, PostgreSQL, public `routemq.telemetry` API, public ClickHouse adapter | These surfaces must be frozen at RC and governed by the release evidence in this ADR. |
| Experimental | TimescaleDB, InfluxDB, IoTDB telemetry adapters | These integrations are outside the v1 release claim, soak requirement, and compatibility freeze. |
| Internal | `routemq.tsdb` and runtime machinery | No compatibility promise applies. The only exception is the ClickHouse adapter re-export through the public telemetry API. |

Core MQTT routing includes documented route registration, parameter matching,
middleware dispatch, controller invocation, and shared-subscription worker
behavior. Redis configuration and the Redis queue backend, MySQL and PostgreSQL
relational integrations and database queue backends, the public telemetry API,
and `ClickHouseTelemetryAdapter` through that API are stable only after the
required evidence supports the release claim.

### RC API freeze

At release candidate, RouteMQ must freeze only the stable surfaces above, their
documented configuration, error behavior, and job envelope schema. Internal and
experimental surfaces remain outside that freeze.

### Qualification protocol

Production qualification requires three separate, non-overlapping 24-hour runs
for a total of 72 hours. Each run must send a deterministic sequence and
correlation identifier at 10,000 MQTT messages per second with an 80/20 QoS
0/QoS 1 mix. Each message must traverse `Application`, routing, one queued job,
one worker, and one ClickHouse telemetry observation.

| Queue backend | Duration | Traffic | Pipeline | Expected logical pipeline executions |
|---|---:|---:|---|---:|
| Redis | 24 hours | 10,000 MQTT messages per second, QoS 0 and QoS 1 at an 80/20 mix | Route, one job, one ClickHouse telemetry observation for every message | approximately 864,000,000 |
| MySQL database queue | 24 hours | 10,000 MQTT messages per second, QoS 0 and QoS 1 at an 80/20 mix | Route, one job, one ClickHouse telemetry observation for every message | approximately 864,000,000 |
| PostgreSQL database queue | 24 hours | 10,000 MQTT messages per second, QoS 0 and QoS 1 at an 80/20 mix | Route, one job, one ClickHouse telemetry observation for every message | approximately 864,000,000 |
| Total | 72 hours across independent runs | 10,000 MQTT messages per second per run | Same full pipeline | approximately 2,592,000,000 |

Each backend-specific run must inject the following controlled faults near hours
6, 12, and 18:

| Queue backend | Near h6 | Near h12 | Near h18 |
|---|---|---|---|
| Redis | MQTT broker restart | Queue worker `SIGKILL` | Redis restart |
| MySQL database queue | Graceful `Application` restart | Queue worker `SIGKILL` | MySQL restart |
| PostgreSQL database queue | ClickHouse restart | Queue worker `SIGTERM` | PostgreSQL restart |

After traffic stops, the run must reconcile source, queue, and ClickHouse
observation ledgers only after every queue, reserved-job set, delayed-job set,
worker, and telemetry buffer has drained. Only one fault may be active at a
time. Every fault window must record start and end timestamps, operator action,
affected component, readiness transition, recovery time, reconciliation evidence,
and throughput and recovery separately from the rest of the run. The benchmark
driver and normal service controls are sufficient. A separate chaos platform is
not required.

### Acceptance criteria

All criteria apply to each backend-specific run unless the row states otherwise.

| Measure | Acceptance threshold | Measurement rule |
|---|---|---|
| Sustained throughput | At least 10,000 MQTT messages per second | Producer accepted count divided by steady-state elapsed time only, excluding warm-up, final drain, and recorded fault windows. |
| QoS 1 loss | No unaccounted loss after the final drain | Every QoS 1 source identifier is present in the route, job, or terminal failed-job record and reconciles to the stated fault-window outcome. |
| QoS 0 loss | At most 0.1% outside recorded fault windows | Missing QoS 0 source identifiers divided by QoS 0 source identifiers sent outside fault windows. |
| Duplicate jobs | At most 0.1% with an idempotent handler | Repeated business-effect attempts for the same source identifier divided by completed logical jobs. Retries that produce no repeated business effect are recorded separately. |
| MQTT-to-handler latency | p99 at most 100 ms | Broker ingress timestamp to handler-start timestamp for messages outside fault windows. |
| Queue completion latency | p99 at most 5 s | Successful enqueue timestamp to terminal successful job completion timestamp for messages outside fault windows. |
| Telemetry shutdown | Graceful drain completes and reports its result | Record telemetry accepted, written, failed, dropped, and drain duration. Hard-crash telemetry loss must be documented by source identifier and fault window. |
| Telemetry completeness | Exactly one primary ClickHouse observation for every successful logical job/source after final drain | Missing, unexpected, or duplicate primary observations fail the run. Terminal failed jobs are disjoint from successful logical jobs and are reported separately. |
| Backlog recovery | Return to the pre-fault queue-depth baseline within 10 minutes | Measure from fault-window end until ready, reserved, and delayed counts return to their baseline band. |
| Process growth | RSS, file descriptor, and asyncio task growth at most 10% | Compare the stable post-warm-up baseline to the final pre-drain sample under the same process topology. |
| Worker integrity | No orphan workers | Process inventory after drain and after shutdown contains no unowned RouteMQ worker process. |
| Runtime integrity | No coroutine warnings | Logs and captured stderr contain no unawaited-coroutine, pending-task-destroyed, or equivalent coroutine lifecycle warning. |
| Configuration integrity | No silent fallback | The selected queue backend, relational backend, and telemetry backend match the recorded configuration for the full run. A selected Redis failure never changes the queue backend. |
| Required integrations | No skipped required integrations | The qualifying MQTT, queue-backend, relational-backend, and ClickHouse checks execute and pass. A skipped check fails the release gate. |

The qualifying MQTT check must exercise `Application` instead of calling
`Router.dispatch()` directly. MQTT, Redis, MySQL, PostgreSQL, and ClickHouse
evidence must use installed extras and real services.

### Evidence Ladder

| Rung | Required evidence | Release effect |
|---|---|---|
| 1. Deterministic contract checks | Job-envelope version validation, fail-fast Redis selection, idempotency accounting, graceful and hard-crash semantics, and no coroutine warnings | Necessary but insufficient. |
| 2. Installed-extra integration checks | Real MQTT through `Application`, Redis queue, MySQL database queue, PostgreSQL database queue, and ClickHouse telemetry write | Skips, missing extras, or bypassed application ingress fail this rung. |
| 3. Container deployment evidence | Image, Compose, extras, services, queue workers, health and readiness configuration, and database benchmark coverage agree | Image or Compose extra mismatch fails this rung. |
| 4. Controlled production soak | The three backend-specific 24-hour runs, fault protocol, reconciliation ledgers, and every acceptance threshold in this ADR | All three runs must pass. |
| 5. Release conformance | Versioning, provenance, SBOM, security, documented production evidence, and an external stable deployment meet the repository's release requirements | Required to claim v1 production proven. |

Before the RC freeze, required release evidence must also close the known
blockers: image and Compose extras mismatch, optional integrations that silently
disable or fall back, Python 3.13 advertising without matching CI coverage, the
unversioned job envelope, skippable required integration checks, MQTT
integration that bypasses `Application`, no live telemetry backend check, Docker
database benchmark omission, the known local TSDB profile failures with
`AsyncMock` warnings, and no external stable deployment.

An external stable deployment is required. The absence of that deployment
prevents the v1 production-proven claim even if internal soak results pass.

### Qualification validity and recordkeeping

A soak result is valid only for its recorded reference environment. Its evidence
record must state the exact benchmark revision, RouteMQ version, Python version,
operating system and kernel, CPU and memory allocation, storage class, container
image digests, MQTT broker and configuration, Redis, MySQL, PostgreSQL, and
ClickHouse versions and configuration, worker topology, queue and telemetry
settings, traffic generator configuration, QoS mix, timestamps, fault windows,
raw counters, latency samples, logs, and reconciliation outputs.

Results cannot be generalized to other hardware, operating systems, broker
settings, database versions, worker counts, or container images without another
recorded run. A passing result is production evidence for that reference
environment only.

## Consequences

- RouteMQ must not claim a production-proven v1 release until it produces all
  required evidence in this ADR, including an external stable deployment.
- Stable APIs have a narrow RC freeze. Experimental and internal surfaces retain
  their existing non-stable status.
- Normal Docker integration tests remain opt-in. A later strict
  `RUN_INTEGRATION_TESTS=required` gate must fail on skipped required tests or
  unavailable Docker before those checks can satisfy the Evidence Ladder.

## References

- [Release conformance](../release-conformance.md)
- [Integration tests](../testing/integration-tests.md)
- [ADR-0010: TSDB Integration: Internal Driver Contract, ClickHouse First](0010-tsdb-driver-registry.md)
