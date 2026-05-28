import json
import logging
import os
import unittest
from unittest.mock import MagicMock, patch

from routemq import observability
from routemq.logging_config import RouteMQJsonFormatter, configure_lifecycle_logging, get_formatter_name


class RouteMQJsonFormatterTests(unittest.TestCase):
    def tearDown(self) -> None:
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


class LoggingEnvironmentTests(unittest.TestCase):
    def test_legacy_log_format_selects_plain_formatter(self) -> None:
        with patch.dict(os.environ, {'LOG_FORMAT': '%(levelname)s:%(message)s'}, clear=True):
            self.assertEqual(get_formatter_name(), 'plain')

    def test_default_formatter_is_json(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_formatter_name(), 'json')


if __name__ == '__main__':
    unittest.main()
