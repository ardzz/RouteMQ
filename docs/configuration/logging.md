# Logging Configuration

RouteMQ emits backend-neutral stdlib logs. New applications default to newline-delimited JSON
(NDJSON) on stdout so Docker, systemd, and log shippers can ingest one event per line without a
RouteMQ-specific agent. Legacy text logging remains available by setting `LOG_FORMATTER=plain`.

## Overview

The logging system supports:

- JSON/NDJSON or legacy plain-text formatting.
- Console output to stdout or stderr.
- Optional rotating file output.
- Context enrichment from RouteMQ observability contextvars.
- Lifecycle-event mirroring for MQTT, router, and queue/job events.
- Field profiles for common backends: OpenTelemetry-style (`otel`), Elastic ECS (`ecs`), Datadog
  (`datadog`), Loki (`loki`), and compact RouteMQ (`routemq`).

RouteMQ does **not** require Datadog, Elastic, Loki, OpenTelemetry, or any other vendor SDK. The JSON
payload is plain Python stdlib logging output that your collector can transform as needed.

## Basic Logging Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_FORMATTER` | `json` | Formatter: `json` for NDJSON or `plain` for legacy text logs. This is authoritative when set. |
| `LOG_FIELD_PROFILE` | `otel` | JSON field profile: `otel`, `ecs`, `datadog`, `loki`, or `routemq`. |
| `LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LOG_TO_CONSOLE` | `true` | Enable console logging when the caller allows console output. |
| `LOG_STREAM` | `stdout` | Console stream: `stdout` or `stderr`. |
| `LOG_INCLUDE_CONTEXT` | `true` | Include RouteMQ correlation/MQTT/queue context from `routemq.observability`. |
| `LOG_LIFECYCLE_EVENTS` | `true` | Mirror known RouteMQ lifecycle events to logs. |
| `LOG_LIFECYCLE_LEVEL` | `INFO` | Log level used for mirrored lifecycle events. |
| `LOG_TO_FILE` | `false` | Enable optional file logging. |
| `LOG_FILE` | `logs/app.log` | File path when `LOG_TO_FILE=true` (relative to project root or absolute). |
| `LOG_FORMAT` | `%(asctime)s - %(name)s - %(levelname)s - %(message)s` | Legacy plain-text format used when `LOG_FORMATTER=plain`. A custom `LOG_FORMAT` without `LOG_FORMATTER` keeps backward-compatible plain logging. |

## JSON Logs

Default configuration:

```env
LOG_FORMATTER=json
LOG_FIELD_PROFILE=otel
LOG_LEVEL=INFO
LOG_TO_CONSOLE=true
LOG_STREAM=stdout
LOG_INCLUDE_CONTEXT=true
LOG_LIFECYCLE_EVENTS=true
LOG_LIFECYCLE_LEVEL=INFO
LOG_TO_FILE=false
```

Example output (`LOG_FIELD_PROFILE=otel`):

```json
{"timestamp":"2026-05-28T03:15:00.000000Z","severity_text":"INFO","severity_number":9,"logger":"RouteMQ.Application","message":"Logging configured","service.name":"routemq-app","deployment.environment.name":"development","correlation_id":null,"trace_id":null,"span_id":null,"trace_flags":null,"event.name":null,"event.domain":null,"routemq.mqtt.topic":null,"attributes":{"formatter":"json","field_profile":"otel"}}
```

The `trace_id`, `span_id`, and `trace_flags` keys are reserved and currently nullable. They are kept
stable so future tracing/span support can correlate logs without changing the log contract.

## Field Profiles

| Profile | Intended use | Notes |
|---------|--------------|-------|
| `otel` | OpenTelemetry-style collectors and generic JSON pipelines | Uses `severity_text`, `severity_number`, `service.name`, `deployment.environment.name`, and `attributes`. |
| `ecs` | Elastic Common Schema pipelines | Emits aliases such as `@timestamp`, `log.level`, `trace.id`, `span.id`, and `labels`. |
| `datadog` | Datadog log pipelines | Emits `service`, `env`, `version`, `dd.service`, `dd.env`, `dd.version`, `dd.trace_id`, and `dd.span_id`. |
| `loki` | Loki/Promtail pipelines | Keeps the OpenTelemetry-style payload and adds low-cardinality `labels`. |
| `routemq` | Compact RouteMQ-native JSON | Nests service, event, error, and RouteMQ-specific fields. |

## Context Enrichment

When `LOG_INCLUDE_CONTEXT=true`, log records include the current RouteMQ observability context. Built-in
MQTT message dispatch, shared-subscription workers, and queue events attach fields such as:

- `correlation_id`
- `routemq.mqtt.topic`
- `routemq.mqtt.actual_topic`
- `routemq.route.pattern`
- `routemq.route.shared`
- `routemq.queue`
- `routemq.job.id`
- `routemq.job.class`
- `routemq.worker.id`

Application code can add context around its own operations:

```python
import logging
from routemq.observability import reset_context, set_context

logger = logging.getLogger("RouteMQ.App")

token = set_context({"tenant": "acme", "feature": "sync"})
try:
    logger.info("Processing tenant message")
finally:
    reset_context(token)
```

Unknown context and `extra={...}` fields are placed in the JSON `attributes` object to avoid schema
collisions.

## Lifecycle Event Logs

`LOG_LIFECYCLE_EVENTS=true` mirrors known internal lifecycle events into the `RouteMQ.Lifecycle` logger.
This gives log-only deployments visibility into framework events without installing a metrics or tracing
exporter.

Known event families include:

- MQTT connection and message events (`mqtt.connect.*`, `mqtt.message.*`).
- Router dispatch events (`router.dispatch.*`).
- Queue enqueue and job events (`queue.enqueue.*`, `queue.job.*`).

The lifecycle bridge only logs known framework events to reduce noise and avoid recursive application
events.

## Plain Text Logs

Set `LOG_FORMATTER=plain` to use traditional Python logging output:

```env
LOG_FORMATTER=plain
LOG_LEVEL=DEBUG
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

Backward compatibility note: if you already set a custom `LOG_FORMAT` and do not set
`LOG_FORMATTER`, RouteMQ treats that as `LOG_FORMATTER=plain`.

## File Logging and Rotation

Console JSON is recommended for containers. File logging remains available when local retention is useful:

```env
LOG_TO_FILE=true
LOG_FILE=logs/app.log
LOG_ROTATION_TYPE=size
LOG_MAX_BYTES=5242880
LOG_BACKUP_COUNT=3
```

### Rotation Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_ROTATION_TYPE` | `size` | Rotation strategy: `size` or `time`. |
| `LOG_MAX_BYTES` | `10485760` | Maximum file size in bytes before size-based rotation (10 MB). |
| `LOG_BACKUP_COUNT` | `5` | Number of backup files to keep. |
| `LOG_ROTATION_WHEN` | `midnight` | Time rotation period: `midnight`, `D`, `H`, `W0`-`W6`, etc. |
| `LOG_ROTATION_INTERVAL` | `1` | Time rotation interval. |
| `LOG_DATE_FORMAT` | `%Y-%m-%d` | Suffix used for time-rotated backup files. |

### Time-based Rotation Example

```env
LOG_TO_FILE=true
LOG_FILE=logs/app.log
LOG_ROTATION_TYPE=time
LOG_ROTATION_WHEN=midnight
LOG_ROTATION_INTERVAL=1
LOG_BACKUP_COUNT=7
LOG_DATE_FORMAT=%Y-%m-%d
```

## Error Handling

If file logging setup fails because the path is not writable, RouteMQ keeps startup resilient and falls
back to the configured console output. If both console and file outputs are disabled or unavailable,
RouteMQ installs a `NullHandler` so `logging.basicConfig()` does not synthesize an unexpected stderr
handler.

## Performance Considerations

- JSON serialization has a small per-record cost; use `LOG_LEVEL=INFO` or higher in production unless
  actively debugging.
- Keep Loki labels low-cardinality. Put tenant IDs, message IDs, and topics in attributes, not labels.
- Prefer stdout/stderr collection in containers over writing log files inside the container filesystem.
- Avoid logging sensitive payloads directly; enrich with IDs and routing metadata instead.

## Log Shipping Recipes

All recipes assume `LOG_FORMATTER=json`. File-based examples also assume:

```env
LOG_TO_FILE=true
LOG_FILE=/app/logs/app.log
```

The default `otel` profile emits `timestamp`, `severity_text`, `severity_number`, `logger`, `message`,
`service.name`, `deployment.environment.name`, `correlation_id`, `trace_id`, `span_id`, `routemq.*`,
`attributes`, and `exception.*`. Use the backend profile called out in each recipe when it gives the
collector native field names.

### Vector

Use the default `otel` profile; Vector reads RouteMQ NDJSON from a file and keeps `routemq.*` plus
`attributes` as structured fields.

```toml
# vector.toml
[sources.routemq]
type = "file"
include = ["/app/logs/app.log"]
read_from = "beginning"

[transforms.routemq_json]
type = "remap"
inputs = ["routemq"]
source = '''
. = parse_json!(.message)
.timestamp = parse_timestamp!(.timestamp, format: "%Y-%m-%dT%H:%M:%S.%fZ")
.level = .severity_text
.service = ."service.name"
.environment = ."deployment.environment.name"
# message, severity_number, routemq.*, attributes, and exception.* stay on the event.
'''

[sinks.stdout]
type = "console"
inputs = ["routemq_json"]

[sinks.stdout.encoding]
codec = "json"
```

### OpenTelemetry Collector

Use the default `otel` profile; the `filelog` receiver maps RouteMQ time, severity, message, service,
environment, and RouteMQ fields into an OTel log record.

```yaml
# otelcol.yaml
receivers:
  filelog/routemq:
    include: ["/app/logs/app.log"]
    start_at: beginning
    operators:
      - type: json_parser
        timestamp:
          parse_from: attributes.timestamp
          layout_type: gotime
          layout: "2006-01-02T15:04:05.999999Z"
        severity:
          parse_from: attributes.severity_text
      - type: move
        from: attributes.message
        to: body
      - type: move
        from: attributes["service.name"]
        to: resource["service.name"]
      - type: move
        from: attributes["deployment.environment.name"]
        to: resource["deployment.environment.name"]

exporters:
  debug: {}

service:
  pipelines:
    logs:
      receivers: [filelog/routemq]
      exporters: [debug]
```

### Fluent Bit

Use the default `otel` profile; Fluent Bit parses the JSON line and uses RouteMQ's timestamp as the
event time.

```ini
# fluent-bit.conf
[SERVICE]
    Parsers_File parsers.conf

[INPUT]
    Name tail
    Path /app/logs/app.log
    Tag routemq
    Parser routemq_json
    Read_from_Head true

[OUTPUT]
    Name stdout
    Match routemq
```

```ini
# parsers.conf
[PARSER]
    Name routemq_json
    Format json
    Time_Key timestamp
    Time_Format %Y-%m-%dT%H:%M:%S.%fZ
    Time_Keep On
```

After parsing, `severity_text`, `severity_number`, `message`, `logger`, `service.name`,
`deployment.environment.name`, `routemq.*`, and `attributes` remain record keys.

### Logstash

Use `LOG_FIELD_PROFILE=routemq` for nested RouteMQ fields that are easy to address in Logstash filters.

```conf
# logstash.conf
input {
  file {
    path => "/app/logs/app.log"
    start_position => "beginning"
    sincedb_path => "/dev/null"
    codec => json
  }
}

filter {
  date {
    match => ["timestamp", "ISO8601"]
    target => "@timestamp"
  }
  mutate {
    rename => { "level" => "[log][level]" }
  }
}

output {
  stdout { codec => json_lines }
}
```

The `routemq` profile keeps `message`, `logger`, `service.name`, `service.env`, `event.*`,
`routemq.*`, `error.*`, and `attributes` in nested JSON objects.

### Grafana Alloy and Loki

Use `LOG_FIELD_PROFILE=loki`; Alloy reads the file, extracts low-cardinality labels, preserves high
cardinality RouteMQ values as structured metadata, and writes to Loki.

```hcl
# config.alloy
local.file_match "routemq" {
  path_targets = [
    { __path__ = "/app/logs/app.log", job = "routemq" },
  ]
}

loki.source.file "routemq" {
  targets    = local.file_match.routemq.targets
  forward_to = [loki.process.routemq.receiver]
}

loki.process "routemq" {
  stage.json {
    expressions = {
      ts             = "timestamp"
      level          = "severity_text"
      message        = "message"
      service_name   = "labels.\"service.name\""
      environment    = "labels.\"deployment.environment.name\""
      component      = "labels.\"routemq.component\""
      queue          = "labels.\"routemq.queue\""
      correlation_id = "correlation_id"
      route_pattern  = "\"routemq.route.pattern\""
    }
  }

  stage.timestamp {
    source = "ts"
    format = "RFC3339Nano"
  }

  stage.labels {
    values = {
      service_name = ""
      environment  = ""
      level        = ""
      component    = ""
      queue        = ""
    }
  }

  stage.structured_metadata {
    values = {
      correlation_id = ""
      route_pattern  = ""
    }
  }

  forward_to = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```

### Elastic with Filebeat

Use `LOG_FIELD_PROFILE=ecs`; Filebeat's `filestream` input decodes NDJSON into Elastic Common Schema
fields.

```yaml
# filebeat.yml
filebeat.inputs:
  - type: filestream
    id: routemq
    paths:
      - /app/logs/app.log
    parsers:
      - ndjson:
          target: ""
          add_error_key: true
          overwrite_keys: true
          expand_keys: true

processors:
  - timestamp:
      field: "@timestamp"
      layouts:
        - "2006-01-02T15:04:05.999999Z"
      test:
        - "2026-05-28T03:15:00.000000Z"

output.elasticsearch:
  hosts: ["http://elasticsearch:9200"]
```

The ECS profile maps RouteMQ fields to `@timestamp`, `log.level`, `log.logger`, `message`,
`service.name`, `service.environment`, `trace.id`, `span.id`, `labels.correlation_id`, `routemq`,
`attributes`, and `error.*`.

### Datadog

Use `LOG_FIELD_PROFILE=datadog`; the Datadog Agent reads the file and sends RouteMQ's Datadog-shaped
JSON attributes.

```yaml
# /etc/datadog-agent/conf.d/routemq.d/conf.yaml
logs:
  - type: file
    path: /app/logs/app.log
    service: routemq-app
    source: python
```

```yaml
# /etc/datadog-agent/datadog.yaml
logs_enabled: true
```

The Datadog profile emits `timestamp`, `status`, `message`, `logger`, `service`, `env`, `version`,
`dd.service`, `dd.env`, `dd.version`, `dd.trace_id`, `dd.span_id`, `event.*`, `routemq`, `attributes`,
and `error.*`.

### Sentry

Use the default `otel` profile; an OpenTelemetry Collector can parse the file and forward logs to
Sentry's OTLP logs endpoint.

```yaml
# otelcol-sentry.yaml
receivers:
  filelog/routemq:
    include: ["/app/logs/app.log"]
    operators:
      - type: json_parser
        timestamp:
          parse_from: attributes.timestamp
          layout_type: gotime
          layout: "2006-01-02T15:04:05.999999Z"
        severity:
          parse_from: attributes.severity_text
      - type: move
        from: attributes.message
        to: body
      - type: move
        from: attributes["service.name"]
        to: resource["service.name"]
      - type: move
        from: attributes["deployment.environment.name"]
        to: resource["deployment.environment.name"]

processors:
  batch: {}

exporters:
  otlphttp/sentry:
    logs_endpoint: ${env:SENTRY_OTLP_LOGS_URL}
    headers:
      x-sentry-auth: "sentry sentry_key=${env:SENTRY_PUBLIC_KEY}"
    compression: gzip
    encoding: proto

service:
  pipelines:
    logs:
      receivers: [filelog/routemq]
      processors: [batch]
      exporters: [otlphttp/sentry]
```

This maps RouteMQ `timestamp` to the OTel log timestamp, `severity_text` to severity, `message` to the
log body, `service.name` and `deployment.environment.name` to resource attributes, and keeps `routemq.*`,
`correlation_id`, `trace_id`, `span_id`, `attributes`, and `exception.*` as log attributes.

### Docker json-file Driver

Use stdout JSON with Docker's default `json-file` driver; Docker wraps each RouteMQ NDJSON line in its
own JSON object.

```yaml
# docker-compose.yml
services:
  routemq:
    image: your-routemq-image
    environment:
      LOG_FORMATTER: json
      LOG_FIELD_PROFILE: otel
      LOG_TO_CONSOLE: "true"
      LOG_STREAM: stdout
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Docker stores events like `{"log":"{...RouteMQ JSON...}\n","stream":"stdout","time":"..."}`.
Downstream shippers should parse Docker's `log` value as JSON, then map the inner RouteMQ `timestamp`,
`severity_text`, `severity_number`, `message`, `service.name`, `deployment.environment.name`,
`routemq.*`, `attributes`, and `exception.*` fields.

## Troubleshooting

### Logs are plain text instead of JSON

- Check whether `LOG_FORMATTER=plain` is set.
- Check whether a legacy `LOG_FORMAT` exists without `LOG_FORMATTER`; this intentionally selects plain
  logs for compatibility.

### Banner text appears in log output

RouteMQ suppresses the startup banner when JSON logging is enabled. If you see banner text in a JSON log
stream, verify `LOG_FORMATTER=json` is set before the application starts.

### Missing log file

- Set `LOG_TO_FILE=true`.
- Verify `LOG_FILE` points to a writable path.
- For containers, prefer stdout logs unless you have a mounted writable volume.
