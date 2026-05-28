# ADR-0005: Observability Stack — Logs, Traces, and Vendor-Neutral Metrics

**Status:** Accepted
**Date:** 2026-05-29
**Sprint:** Sprint 06A-C

## Context

RouteMQ needed operator-facing observability for message handling, queue work, application lifecycle,
and runtime failures. The framework needed logs, traces, and metrics without coupling the core package
to a telemetry vendor such as Datadog, Sentry, Elastic, the OpenTelemetry SDK, or a Prometheus client.

The design also had to keep the default install lightweight. RouteMQ is a framework dependency for user
applications, so observability support must not force every application to inherit a vendor runtime,
network exporter, background thread model, or deployment contract it did not choose.

## Decision

Ship a layered, vendor-neutral observability stack:

1. **Logs-first JSON exposition** from Sprint 06A, released across v0.18 and v0.19, so operators get
   structured lifecycle and request evidence with no optional dependency.
2. **W3C tracing spans** from Sprint 06B, released in v0.19, so trace context can cross broker,
   controller, middleware, and queue boundaries without binding RouteMQ to one tracing backend.
3. **Vendor-neutral `/metrics` endpoint** from Sprint 06C in PR #65, backed by the optional
   `routemq[prometheus]` extra rather than a hard dependency.
4. **Stdlib-only core by default.** The base package exposes hooks and structured data; optional extras
   provide concrete exporters only when an operator opts in.
5. **Span, metric, and trace hook seams isolate user code from observability plumbing.** Application
   handlers see stable framework contracts while operators decide how to collect and forward telemetry.

## Consequences

### Positive

- The default install has zero hard dependency on observability libraries.
- Operators can route JSON logs, trace context, and metrics to their existing platform without RouteMQ
  choosing that platform for them.
- The hook seam keeps core message handling testable and avoids exporter-specific side effects in
  controllers or middleware.
- Prometheus support is available for deployments that want it without making Prometheus the only path.

### Negative

- Multiprocess metrics require the optional extra and a correctly configured `PROMETHEUS_MULTIPROC_DIR`.
- Metric label cardinality is the operator's responsibility; RouteMQ exposes labels but cannot know every
  deployment's cardinality budget.
- Vendor-specific dashboards and alerts remain downstream integration work rather than framework code.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Vendor lock-in | Coupling core to one telemetry vendor would make RouteMQ harder to adopt in heterogeneous operations environments. |
| OpenTelemetry SDK as a core dependency | The SDK is useful but too heavy for the base install and would split the ecosystem around exporter choices. |
| Do nothing | Operators would remain blind to lifecycle failures, slow handlers, and queue behavior. |

## Related

- PR #61: Sprint 06A and 06B observability work released in v0.19.0.
- PR #65: Sprint 06C metrics endpoint and optional Prometheus integration.
