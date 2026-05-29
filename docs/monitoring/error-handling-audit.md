# Error Handling Audit

**Date:** 2026-05-29  
**Scope:** `routemq/` and `bootstrap/` exception handlers  
**Sprint:** Sprint 06F fail-fast logging audit

## Purpose

This audit closes the Sprint 06F review of currently-swallowed exceptions in RouteMQ framework
internals. The goal is to make interesting failures visible at `WARNING` or higher with traceback
context, preserve exception chains where a wrapper exception is still required by existing retry
semantics, and document every intentionally accepted best-effort swallow.

## Methodology

The sweep started with the required static commands:

```bash
rg -n 'except\s+[A-Za-z_]+(\s+as\s+\w+)?\s*:' routemq bootstrap
rg -n '^\s*pass\s*$' routemq bootstrap -B 3
```

The final inventory was expanded with `rg -n '^\s*except\b' routemq bootstrap` so tuple catches
such as `except (ValueError, RuntimeError):` were also included. Each site was classified as:

- **Fix** — a swallowed error needed stronger fail-fast logging (`WARNING` or higher, traceback,
  and useful context).
- **Re-raise** — a wrapper exception was retained for compatibility, but the original exception
  chain is now preserved with `raise ... from exc`.
- **Accept** — the block is intentionally best-effort, already re-raises, or is covered by lifecycle
  event mirroring; rationale is recorded here and accepted swallows are annotated in code where
  changing behavior would be misleading.

Lifecycle coverage was checked against Sprint 06A mirroring. Rows that already emit
`mqtt.message.failed`, `router.dispatch.failed`, `queue.enqueue.failed`, `queue.job.failed`, or
related lifecycle events note that coverage explicitly.

## Audit table

| File:Line | Exception caught | Classification | Rationale | Test added |
|---|---|---|---|---|
| `bootstrap/app.py:39` | `PackageNotFoundError` | Accept | Source checkout version fallback is intentional and not an operational failure. | N/A |
| `bootstrap/app.py:97` | `Exception as e` | Accept | Router auto-discovery can fail before scaffolding; startup keeps an empty router and logs a warning. | N/A |
| `bootstrap/app.py:202` | `Exception` | Accept | Not swallowed; coroutine is closed and the scheduling exception is re-raised to the outer callback handler. | N/A |
| `bootstrap/app.py:206` | `Exception as e` | Fix | Main MQTT callback previously swallowed parse/scheduling failures without traceback or `mqtt.message.failed`; now logs with `exc_info=True` and emits lifecycle. | `tests/unit/bootstrap/test_app.py::TestApplicationMqtt::test_on_message_logs_and_lifecycles_scheduling_failure` |
| `bootstrap/app.py:231` | `Exception as exc` | Accept | Already re-raises after `mqtt.message.failed`; Sprint 06A lifecycle mirroring covers the failure path. | N/A |
| `bootstrap/app.py:275` | `(ValueError, RuntimeError)` | Accept | Signal handler installation may be unavailable outside the main thread; DEBUG log is sufficient. | N/A |
| `bootstrap/app.py:284` | `(ValueError, RuntimeError)` | Accept | Best-effort shutdown signal restoration; failure cannot safely alter cleanup. | N/A |
| `bootstrap/app.py:320` | `KeyboardInterrupt` | Accept | Expected graceful shutdown path, not an error. | N/A |
| `routemq/retry.py:95` | `BaseException as exc` | Accept | Retry helper re-raises when attempts are exhausted or the exception is not retryable; no swallow. | N/A |
| `routemq/worker_manager.py:55` | `Exception as e` | Fix | Worker router discovery fallback now keeps the empty router behavior but includes traceback and router context. | `tests/unit/core/test_worker_manager_process.py::WorkerProcessSetupRouterTests::test_setup_router_falls_back_to_empty_on_exception` |
| `routemq/worker_manager.py:113` | `Exception as e` | Fix | Worker MQTT callback parse/scheduling failures now emit `mqtt.message.failed` and log with traceback. | `tests/unit/core/test_worker_manager_process.py::WorkerProcessOnMessageTests::test_on_message_logs_and_lifecycles_schedule_failure` |
| `routemq/worker_manager.py:137` | `Exception as exc` | Fix | Scheduled dispatch future failures already have router lifecycle coverage when dispatch starts; callback logging now keeps traceback. | `tests/unit/core/test_worker_manager_process.py::WorkerProcessOnMessageTests::test_schedule_dispatch_callback_logs_future_failure_with_traceback` |
| `routemq/worker_manager.py:162` | `Exception as exc` | Accept | Already emits `mqtt.message.failed` and re-raises from the async dispatch path. | N/A |
| `routemq/worker_manager.py:186` | `OSError as exc` | Accept | Expected startup network failures are reported and the child exits; non-network `OSError` still re-raises. | N/A |
| `routemq/worker_manager.py:203` | `KeyboardInterrupt` | Accept | Expected process shutdown path. | N/A |
| `routemq/worker_manager.py:304` | `(OSError, RuntimeError) as exc` | Accept | Per-worker process start is best-effort; failure logs a warning and remaining slots continue. | N/A |
| `routemq/tinker.py:47` | `ImportError` | Accept | Rich is optional for the REPL; fallback remains functional. | N/A |
| `routemq/tinker.py:61` | `ImportError` | Accept | Figlet banner is cosmetic; Rich tables still work. | N/A |
| `routemq/tinker.py:158` | `TypeError` | Accept | Scalar REPL rows are rendered as a single value column. | N/A |
| `routemq/tinker.py:314` | `RuntimeError` | Accept | No active REPL loop, so `asyncio.run` is the safe fallback. | N/A |
| `routemq/tinker.py:364` | `ImportError as e` | Accept | Optional app model import failures are displayed to the REPL user. | N/A |
| `routemq/tinker.py:367` | `Exception as e` | Accept | Tinker model discovery is convenience-only and prints a warning. | N/A |
| `routemq/tinker.py:471` | `KeyboardInterrupt` | Accept | Interactive Ctrl+C exits cleanly. | N/A |
| `routemq/tinker.py:474` | `Exception as e` | Accept | Interactive startup errors are printed with traceback for the user. | N/A |
| `routemq/tinker.py:507` | `RuntimeError` | Accept | No running event loop; `asyncio.run` is the intended fallback. | N/A |
| `routemq/settings.py:41` | `ValueError` | Accept | Selected settings intentionally keep legacy fallback behavior when requested; otherwise re-raise. | N/A |
| `routemq/settings.py:55` | `ValueError` | Accept | Selected settings intentionally keep legacy fallback behavior when requested; otherwise re-raise. | N/A |
| `routemq/scaffold/scaffolder.py:148` | `ImportError as exc` | Accept | Re-raised with actionable CLI extra requirement and original cause. | N/A |
| `routemq/scaffold/scaffolder.py:157` | `metadata.PackageNotFoundError` | Accept | Source checkout scaffold uses a sentinel version. | N/A |
| `routemq/scaffold/scaffolder.py:176` | `ImportError` | Accept | Rich is optional; plain success output is sufficient. | N/A |
| `routemq/scaffold/prompts.py:11` | `ImportError` | Accept | Re-raised with an actionable CLI extra requirement and intentionally suppresses packaging internals. | N/A |
| `routemq/router.py:171` | `Exception as exc` | Accept | Already emits `router.dispatch.failed` and re-raises; Sprint 06A lifecycle mirroring covers this path. | N/A |
| `routemq/observability.py:217` | `ValueError` | Accept | Hex validation helper returns `False`; invalid inbound trace IDs are expected input. | N/A |
| `routemq/observability.py:227` | `ValueError` | Accept | Trace flag validation helper returns `False`; invalid inbound flags are expected input. | N/A |
| `routemq/observability.py:263` | `Exception` | Accept | Out of scope: span hook isolation is intentionally DEBUG-only and must not break business logic. | N/A |
| `routemq/observability.py:416` | `(TypeError, json.JSONDecodeError)` | Accept | Invalid or non-JSON payload observability metadata simply means no context. | N/A |
| `routemq/observability.py:430` | `ValueError` | Accept | Unregister callbacks are idempotent; missing hook removal is intentionally silent. | N/A |
| `routemq/observability.py:444` | `ValueError` | Accept | Unregister callbacks are idempotent; missing hook removal is intentionally silent. | N/A |
| `routemq/observability.py:458` | `ValueError` | Accept | Unregister callbacks are idempotent; missing hook removal is intentionally silent. | N/A |
| `routemq/observability.py:483` | `Exception` | Accept | Out of scope: trace hook isolation is intentionally DEBUG-only and must not break business logic. | N/A |
| `routemq/observability.py:494` | `Exception` | Accept | Out of scope: metric hook isolation is intentionally DEBUG-only and must not break business logic. | N/A |
| `routemq/mqtt_utils.py:37` | `(json.JSONDecodeError, UnicodeDecodeError)` | Accept | Invalid JSON is a valid MQTT payload; raw bytes are dispatched. | N/A |
| `routemq/mqtt_utils.py:139` | `(TypeError, ValueError)` | Accept | Older/mock Paho callables may not expose signatures; legacy reconnect kwargs are used. | N/A |
| `routemq/logging_config.py:213` | `PackageNotFoundError` | Accept | Source checkout logging metadata uses the dev sentinel version. | N/A |
| `routemq/logging_config.py:510` | `OSError` | Accept | File logging is optional; DEBUG traceback plus console/NullHandler fallback keeps startup resilient. | N/A |
| `routemq/cli.py:124` | `Exception as e` | Accept | Generated sample middleware logs and re-raises; no swallow. | N/A |
| `routemq/cli.py:201` | `OSError as exc` | Accept | Network startup failures become user-facing `SystemExit`; non-network errors re-raise. | N/A |
| `routemq/redis_manager.py:10` | `ImportError` | Accept | Redis package is optional; runtime init logs if Redis is enabled without the dependency. | N/A |
| `routemq/redis_manager.py:95` | `Exception as e` | Fix | Redis initialization failure now logs at WARNING with traceback and sanitized host/port/db context. | `tests/unit/core/test_redis_manager.py::TestRedisManager::test_initialize_failure_disables_manager_and_returns_false` |
| `routemq/redis_manager.py:146` | `Exception as e` | Accept | Redis GET helper returns miss sentinel after ERROR log; optional cache should not break callers. | N/A |
| `routemq/redis_manager.py:180` | `Exception as e` | Accept | Redis SET helper returns `False` after ERROR log; optional cache should not break callers. | N/A |
| `routemq/redis_manager.py:201` | `Exception as e` | Accept | Redis INCR helper returns sentinel after ERROR log; optional counter should not break callers. | N/A |
| `routemq/redis_manager.py:223` | `Exception as e` | Accept | Redis EXPIRE helper returns `False` after ERROR log; expiration is best-effort. | N/A |
| `routemq/redis_manager.py:243` | `Exception as e` | Accept | Redis DELETE helper returns zero after ERROR log; cleanup is best-effort. | N/A |
| `routemq/redis_manager.py:264` | `Exception as e` | Accept | Redis EXISTS helper returns `False` after ERROR log; optional cache should not break callers. | N/A |
| `routemq/redis_manager.py:284` | `Exception as e` | Accept | Redis TTL helper returns missing-key sentinel after ERROR log. | N/A |
| `routemq/redis_manager.py:305` | `Exception as e` | Accept | Redis HGET helper returns miss sentinel after ERROR log. | N/A |
| `routemq/redis_manager.py:333` | `Exception as e` | Accept | Redis HSET helper returns zero changed fields after ERROR log. | N/A |
| `routemq/redis_manager.py:354` | `json.JSONDecodeError as e` | Accept | Malformed cached JSON behaves as a cache miss after ERROR log. | N/A |
| `routemq/redis_manager.py:385` | `(TypeError, ValueError) as e` | Accept | Unserializable cache values report write failure after ERROR log. | N/A |
| `routemq/queue/queue_worker.py:106` | `Exception as e` | Fix | Worker-loop polling failures now log with traceback and queue context before continuing. | `tests/unit/core/test_queue_worker_extra.py::QueueWorkerWorkLoopTests::test_work_catches_pop_exception_and_continues` |
| `routemq/queue/queue_worker.py:173` | `asyncio.TimeoutError as exc` | Re-raise | Timeout wrapper keeps existing retry semantics but now preserves the original `TimeoutError` as `__cause__`; `queue.job.timed_out` still fires. | `tests/unit/core/test_queue_worker_extra.py::QueueWorkerProcessJobTests::test_timeout_exception_chain_is_preserved_for_failure_handling` |
| `routemq/queue/queue_worker.py:182` | `Exception as e` | Fix | Job execution failures now log with traceback; retry/fail lifecycle events remain unchanged. | `tests/unit/core/test_queue_worker_extra.py::QueueWorkerProcessJobTests::test_failure_with_remaining_tries_releases_job` |
| `routemq/queue/queue_worker.py:206` | `Exception as unserialize_error` | Fix | Corrupted payload cleanup now logs with traceback before deleting the unrecoverable job. | `tests/unit/core/test_queue_worker_extra.py::QueueWorkerProcessJobTests::test_corrupted_payload_is_deleted` |
| `routemq/queue/queue_worker.py:293` | `Exception as e` | Fix | Failed-job persistence/handler errors remain swallowed to avoid recursion but now include traceback. | `tests/unit/core/test_queue_worker_extra.py::QueueWorkerFailJobTests::test_fail_job_swallows_exceptions` |
| `routemq/queue/queue_worker.py:310` | `RuntimeError` | Accept | Compatibility fallback for callers outside a running event loop. | N/A |
| `routemq/queue/queue_manager.py:200` | `Exception as exc` | Accept | Already emits `queue.enqueue.failed` and re-raises; Sprint 06A lifecycle mirroring covers this path. | N/A |
| `routemq/queue/queue_manager.py:244` | `Exception as exc` | Accept | Already emits `queue.enqueue.failed` and re-raises; Sprint 06A lifecycle mirroring covers this path. | N/A |
| `routemq/queue/queue_manager.py:287` | `Exception as exc` | Accept | Already emits `queue.enqueue.failed` and re-raises for the failing bulk job. | N/A |
| `routemq/queue/redis_queue.py:68` | `Exception as e` | Accept | Push logs ERROR and re-raises; no swallow. | N/A |
| `routemq/queue/redis_queue.py:95` | `Exception as e` | Accept | Delayed migration is best-effort and retried on later polls after ERROR log. | N/A |
| `routemq/queue/redis_queue.py:128` | `Exception as e` | Accept | Polling returns `None` after ERROR log so the worker can continue retrying. | N/A |
| `routemq/queue/redis_queue.py:174` | `Exception as e` | Accept | Release logs ERROR and re-raises; no swallow. | N/A |
| `routemq/queue/redis_queue.py:200` | `Exception as e` | Accept | Delete logs ERROR and re-raises; no swallow. | N/A |
| `routemq/queue/redis_queue.py:248` | `Exception as e` | Accept | Failed-job persistence errors are logged; retry/fail semantics stay unchanged. | N/A |
| `routemq/queue/redis_queue.py:268` | `Exception as e` | Accept | Queue size is observational and returns zero after ERROR log. | N/A |
| `routemq/queue/database_queue.py:53` | `Exception as e` | Accept | Push rolls back, logs ERROR, and re-raises; no swallow. | N/A |
| `routemq/queue/database_queue.py:103` | `Exception as e` | Accept | Polling returns `None` after ERROR log so the worker can continue retrying. | N/A |
| `routemq/queue/database_queue.py:138` | `Exception as e` | Accept | Release rolls back, logs ERROR, and re-raises; no swallow. | N/A |
| `routemq/queue/database_queue.py:162` | `Exception as e` | Accept | Delete rolls back, logs ERROR, and re-raises; no swallow. | N/A |
| `routemq/queue/database_queue.py:195` | `Exception as e` | Accept | Failed-job persistence rolls back, logs ERROR, and re-raises to the worker failure handler. | N/A |
| `routemq/queue/database_queue.py:219` | `Exception as e` | Accept | Queue size is observational and returns zero after ERROR log. | N/A |
| `routemq/router_registry.py:50` | `ImportError as e` | Accept | Missing `app.routers` is valid before scaffolding; empty router remains usable. | N/A |
| `routemq/router_registry.py:54` | `Exception as e` | Accept | Discovery errors are logged and manual registration can still be used. | N/A |
| `routemq/router_registry.py:81` | `ImportError as e` | Accept | One bad router module should not hide other modules; ERROR log identifies it. | N/A |
| `routemq/router_registry.py:84` | `Exception as e` | Accept | One bad router module should not hide other modules; ERROR log identifies it. | N/A |
| `routemq/scaffold/templates/base/app/middleware/example_middleware.py:23` | `Exception as exc` | Accept | Generated middleware template logs and re-raises; no swallow. | N/A |

## Out of scope: observability hook isolation

Hook isolation in `routemq/observability.py` is INTENTIONALLY silent (Sprint 06B-confirmed design)
and OUT OF SCOPE for this audit. Hook handler failures are logged at DEBUG inside `_emit_span`,
`metric()`, `trace()`, and `lifecycle()`.

## Principle audit resolution

| Reference | Rows | Status | Notes |
|---|---|---|---|
| P1-9 | `routemq/queue/queue_worker.py:106`, `:173`, `:182`, `:206`, `:293` | Fixed / Re-raise | Queue worker loop and job failure paths now log tracebacks; timeout wrapper preserves `TimeoutError.__cause__`; lifecycle rows already cover normal retry/fail/dead-letter events. |
| P1-10 | `routemq/redis_manager.py:95`, `:146`, `:180`, `:201`, `:223`, `:243`, `:264`, `:284`, `:305`, `:333`, `:354`, `:385` | Fixed / Accepted-with-rationale | Redis init failure now logs WARNING with traceback and connection context; helper sentinels remain accepted optional-cache behavior after ERROR logs. |
| P1-11 | `routemq/worker_manager.py:55`, `:113`, `:137`, `:162`, `:186`, `:203`, `:304` | Fixed / Already-covered-by-06A / Accepted-with-rationale | Worker message callback and future failure logs now include traceback; async dispatch already emits `mqtt.message.failed`; process startup remains best-effort. |
| P2-18 | `bootstrap/app.py:206`, `:231`; `routemq/router.py:171`; queue enqueue rows in `routemq/queue/queue_manager.py` | Fixed / Already-covered-by-06A | Main MQTT callback now emits `mqtt.message.failed` for pre-dispatch failures; router and enqueue failures already emit lifecycle events and re-raise. |

## Classification counts

- Total `except` blocks audited: **87**
- Fix: **9**
- Re-raise: **1**
- Accept: **77**
