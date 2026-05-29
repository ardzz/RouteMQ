import json
import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from routemq import observability
from routemq import logging_config
from routemq.logging_config import (
    RouteMQJsonFormatter,
    build_formatter,
    configure_lifecycle_logging,
    configure_logging,
    env_bool,
    get_formatter_name,
)


class RouteMQJsonFormatterTests(unittest.TestCase):
    def tearDown(self) -> None:
        configure_lifecycle_logging(enabled=False)
        observability.clear_hooks()

    def test_otel_profile_includes_context_and_unknown_extra_attributes(self) -> None:
        formatter = RouteMQJsonFormatter(field_profile='otel')
        token = observability.set_context(
            {
                'correlation_id': 'corr-1',
                'mqtt_topic': 'devices/1/status',
                'route_pattern': 'devices/{device_id}/status',
                'tenant': 'acme',
            }
        )
        try:
            record = logging.getLogger('RouteMQ.Test').makeRecord(
                'RouteMQ.Test',
                logging.INFO,
                __file__,
                10,
                'hello %s',
                ('world',),
                None,
                extra={'custom_value': 'kept'},
            )
            payload = json.loads(formatter.format(record))
        finally:
            observability.reset_context(token)

        self.assertEqual(payload['message'], 'hello world')
        self.assertEqual(payload['severity_text'], 'INFO')
        self.assertEqual(payload['severity_number'], 9)
        self.assertEqual(payload['correlation_id'], 'corr-1')
        self.assertIsNone(payload['trace_id'])
        self.assertIsNone(payload['span_id'])
        self.assertIsNone(payload['trace_flags'])
        self.assertEqual(payload['routemq.mqtt.topic'], 'devices/1/status')
        self.assertEqual(payload['routemq.route.pattern'], 'devices/{device_id}/status')
        self.assertEqual(payload['attributes']['tenant'], 'acme')
        self.assertEqual(payload['attributes']['custom_value'], 'kept')

    def test_otel_profile_includes_active_span_context(self) -> None:
        formatter = RouteMQJsonFormatter(field_profile='otel')
        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with observability.start_span('log.span') as span:
                self.assertIsNotNone(span)
                span_context = observability.snapshot_context()
                trace_id = span_context['trace_id']
                span_id = span_context['span_id']
                record = logging.getLogger('RouteMQ.Test').makeRecord(
                    'RouteMQ.Test', logging.INFO, __file__, 10, 'span log', (), None
                )
                payload = json.loads(formatter.format(record))

        self.assertEqual(payload['trace_id'], trace_id)
        self.assertEqual(payload['span_id'], span_id)
        self.assertEqual(payload['trace_flags'], '01')
        self.assertIsNone(payload['parent_span_id'])

    def test_ecs_profile_emits_elastic_aliases(self) -> None:
        formatter = RouteMQJsonFormatter(field_profile='ecs')
        record = logging.getLogger('RouteMQ.Test').makeRecord(
            'RouteMQ.Test', logging.ERROR, __file__, 10, 'boom', (), None, extra={'trace_id': 't1', 'span_id': 's1'}
        )

        payload = json.loads(formatter.format(record))

        self.assertIn('@timestamp', payload)
        self.assertEqual(payload['log.level'], 'error')
        self.assertEqual(payload['trace.id'], 't1')
        self.assertEqual(payload['span.id'], 's1')

    def test_datadog_profile_emits_datadog_aliases(self) -> None:
        formatter = RouteMQJsonFormatter(field_profile='datadog')
        record = logging.getLogger('RouteMQ.Test').makeRecord(
            'RouteMQ.Test', logging.WARNING, __file__, 10, 'warn', (), None, extra={'trace_id': 't2', 'span_id': 's2'}
        )

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload['status'], 'warn')
        self.assertEqual(payload['dd.trace_id'], 't2')
        self.assertEqual(payload['dd.span_id'], 's2')
        self.assertIn('dd.service', payload)

    def test_loki_profile_adds_service_and_queue_labels(self) -> None:
        formatter = RouteMQJsonFormatter(field_profile='loki')
        record = logging.getLogger('RouteMQ.Test').makeRecord(
            'RouteMQ.Test',
            logging.INFO,
            __file__,
            10,
            'queued',
            (),
            None,
            extra={'source': 'queue-worker', 'queue': 'emails'},
        )

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload['labels']['routemq.component'], 'queue-worker')
        self.assertEqual(payload['labels']['routemq.queue'], 'emails')
        self.assertEqual(payload['labels']['severity_text'], 'INFO')

    def test_routemq_profile_nests_routemq_fields_and_known_error(self) -> None:
        formatter = RouteMQJsonFormatter(field_profile='routemq')
        record = logging.getLogger('RouteMQ.Test').makeRecord(
            'RouteMQ.Test',
            logging.ERROR,
            __file__,
            10,
            'failed',
            (),
            None,
            extra={'error': 'QueueTimeout', 'worker_id': 'worker-1'},
        )

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload['level'], 'error')
        self.assertEqual(payload['routemq']['worker_id'], 'worker-1')
        self.assertEqual(payload['error']['type'], 'QueueTimeout')
        self.assertIsNone(payload['error']['message'])
        self.assertIsNone(payload['error']['stacktrace'])

    def test_formatter_serializes_exception_info(self) -> None:
        formatter = RouteMQJsonFormatter(field_profile='otel')

        try:
            raise RuntimeError('handler exploded')
        except RuntimeError:
            record = logging.getLogger('RouteMQ.Test').makeRecord(
                'RouteMQ.Test', logging.ERROR, __file__, 10, 'boom', (), sys.exc_info()
            )

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload['exception.type'], 'RuntimeError')
        self.assertEqual(payload['exception.message'], 'handler exploded')
        self.assertIn('RuntimeError: handler exploded', payload['exception.stacktrace'])

    def test_formatter_serializes_nested_unknown_attributes_safely(self) -> None:
        formatter = RouteMQJsonFormatter(field_profile='otel', include_context=False)
        record = logging.getLogger('RouteMQ.Test').makeRecord(
            'RouteMQ.Test',
            logging.INFO,
            __file__,
            10,
            'custom',
            (),
            None,
            extra={'attributes': {'nested': {'answer': 42}, 'items': ('a', object())}},
        )

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload['attributes']['nested'], {'answer': 42})
        self.assertEqual(payload['attributes']['items'][0], 'a')
        self.assertTrue(payload['attributes']['items'][1].startswith('<object object at '))

    def test_lifecycle_logging_mirrors_known_events(self) -> None:
        fake_logger = MagicMock()

        with patch('routemq.logging_config.logging.getLogger', return_value=fake_logger):
            configure_lifecycle_logging(enabled=True, level=logging.WARNING)

        observability.lifecycle('queue.job.succeeded', {'queue': 'emails'})

        fake_logger.log.assert_called_once()
        level, message = fake_logger.log.call_args.args[:2]
        extra = fake_logger.log.call_args.kwargs['extra']
        self.assertEqual(level, logging.WARNING)
        self.assertEqual(message, 'RouteMQ lifecycle event')
        self.assertEqual(extra['event.name'], 'queue.job.succeeded')
        self.assertEqual(extra['event.domain'], 'queue')
        self.assertEqual(extra['queue'], 'emails')

    def test_lifecycle_logging_ignores_unknown_events(self) -> None:
        fake_logger = MagicMock()

        with patch('routemq.logging_config.logging.getLogger', return_value=fake_logger):
            configure_lifecycle_logging(enabled=True, level=logging.INFO)

        observability.lifecycle('custom.event', {'queue': 'emails'})

        fake_logger.log.assert_not_called()

    def test_lifecycle_logging_unregisters_previous_hook_when_disabled(self) -> None:
        unregister = MagicMock()

        with patch.object(logging_config, '_lifecycle_unregister', unregister):
            configure_lifecycle_logging(enabled=False)
            unregister.assert_called_once_with()
            self.assertIsNone(logging_config._lifecycle_unregister)


class LoggingEnvironmentTests(unittest.TestCase):
    def tearDown(self) -> None:
        logging.getLogger('RouteMQ.Logging').handlers.clear()

    def test_env_bool_handles_default_and_truthy_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(env_bool('MISSING_FLAG', True))
            self.assertFalse(env_bool('MISSING_FLAG', False))

        for value in ('1', 'true', 'yes', 'on'):
            with patch.dict(os.environ, {'FEATURE_FLAG': value}, clear=True):
                self.assertTrue(env_bool('FEATURE_FLAG', False))

        with patch.dict(os.environ, {'FEATURE_FLAG': '0'}, clear=True):
            self.assertFalse(env_bool('FEATURE_FLAG', True))

    def test_explicit_formatter_overrides_legacy_log_format(self) -> None:
        with patch.dict(os.environ, {'LOG_FORMATTER': ' JSON ', 'LOG_FORMAT': '%(message)s'}, clear=True):
            self.assertEqual(get_formatter_name(), 'json')

    def test_legacy_log_format_selects_plain_formatter(self) -> None:
        with patch.dict(os.environ, {'LOG_FORMAT': '%(levelname)s:%(message)s'}, clear=True):
            self.assertEqual(get_formatter_name(), 'plain')

    def test_legacy_log_format_named_json_is_supported(self) -> None:
        with patch.dict(os.environ, {'LOG_FORMAT': 'json'}, clear=True):
            self.assertEqual(get_formatter_name(), 'json')

    def test_default_formatter_is_json(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_formatter_name(), 'json')

    def test_build_formatter_returns_plain_formatter_for_plain_mode(self) -> None:
        with patch.dict(os.environ, {'LOG_FORMAT': '%(levelname)s:%(message)s'}, clear=True):
            formatter = build_formatter('plain')

        self.assertIsInstance(formatter, logging.Formatter)
        self.assertNotIsInstance(formatter, RouteMQJsonFormatter)

    def test_build_formatter_honors_json_field_profile_and_context_flag(self) -> None:
        with patch.dict(os.environ, {'LOG_INCLUDE_CONTEXT': 'false'}, clear=True):
            formatter = build_formatter('json', 'datadog')

        self.assertIsInstance(formatter, RouteMQJsonFormatter)
        assert isinstance(formatter, RouteMQJsonFormatter)
        self.assertEqual(formatter.field_profile, 'datadog')
        self.assertFalse(formatter.include_context)

    def test_configure_logging_uses_null_handler_when_outputs_disabled(self) -> None:
        env = {'LOG_TO_CONSOLE': 'false', 'LOG_TO_FILE': 'false', 'LOG_LIFECYCLE_EVENTS': 'false'}
        with patch.dict(os.environ, env, clear=True):
            with patch('routemq.logging_config.logging.basicConfig') as basic_config:
                with patch('routemq.logging_config.configure_lifecycle_logging') as lifecycle_logging:
                    settings = configure_logging(log_to_console=True)

        self.assertEqual(settings.formatter, 'json')
        self.assertFalse(settings.lifecycle_events)
        handlers = basic_config.call_args.kwargs['handlers']
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], logging.NullHandler)
        lifecycle_logging.assert_called_once_with(enabled=False, level=logging.INFO)

    def test_configure_logging_falls_back_to_null_handler_when_file_setup_fails(self) -> None:
        fake_logger = MagicMock()

        with patch.dict(os.environ, {'LOG_TO_CONSOLE': 'false', 'LOG_TO_FILE': 'true'}, clear=True):
            with patch('routemq.logging_config._build_file_handler', side_effect=OSError('denied')):
                with patch('routemq.logging_config.logging.getLogger', return_value=fake_logger):
                    with patch('routemq.logging_config.logging.basicConfig') as basic_config:
                        with patch('routemq.logging_config.configure_lifecycle_logging'):
                            configure_logging(log_to_console=True)

        handlers = basic_config.call_args.kwargs['handlers']
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], logging.NullHandler)
        fake_logger.debug.assert_called_once()

    def test_service_version_prefers_env_then_package_metadata(self) -> None:
        with patch.dict(os.environ, {'SERVICE_VERSION': '9.8.7'}, clear=True):
            self.assertEqual(logging_config._service_version(), '9.8.7')

        with patch.dict(os.environ, {}, clear=True):
            with patch('routemq.logging_config.version', return_value='1.2.3'):
                self.assertEqual(logging_config._service_version(), '1.2.3')


if __name__ == '__main__':
    unittest.main()
