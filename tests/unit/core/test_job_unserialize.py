import json
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from routemq.job import Job


class RegisteredRegressionJob(Job):
    async def handle(self) -> None:
        return None


class UnregisteredRegressionJob(Job):
    async def handle(self) -> None:
        return None


class TestJobUnserializeAllowList(unittest.TestCase):
    def setUp(self) -> None:
        self._allowed_classes = set(Job._allowed_classes)
        Job._allowed_classes.clear()

    def tearDown(self) -> None:
        Job._allowed_classes.clear()
        Job._allowed_classes.update(self._allowed_classes)

    def make_payload(self, class_name: str, data: Mapping[str, Any] | None = None) -> str:
        return json.dumps({'class': class_name, 'data': dict(data or {})})

    def test_full_legacy_unversioned_payload_deserializes(self) -> None:
        Job.register(RegisteredRegressionJob)
        payload = json.dumps(
            {
                'class': f'{RegisteredRegressionJob.__module__}.{RegisteredRegressionJob.__name__}',
                'data': {'value': 'legacy'},
                'observability': {'trace_id': 'legacy-trace'},
                'max_tries': 7,
                'timeout': 45,
                'retry_after': 9,
                'retry_backoff_enabled': True,
                'retry_backoff_max_delay': 30.0,
                'retry_backoff_jitter': 0.25,
                'queue': 'legacy',
            }
        )

        job = Job.unserialize(payload)

        self.assertIsInstance(job, RegisteredRegressionJob)
        self.assertEqual(getattr(job, 'value'), 'legacy')
        self.assertEqual(job._observability_context, {'trace_id': 'legacy-trace'})
        self.assertEqual(
            (
                job.max_tries,
                job.timeout,
                job.retry_after,
                job.retry_backoff_enabled,
                job.retry_backoff_max_delay,
                job.retry_backoff_jitter,
                job.queue,
            ),
            (7, 45, 9, True, 30.0, 0.25, 'legacy'),
        )

    def test_registered_job_class_deserializes(self) -> None:
        """Allow-listed job class deserializes to the expected Job subclass."""
        Job.register(RegisteredRegressionJob)

        job = Job.unserialize(
            self.make_payload(
                f'{RegisteredRegressionJob.__module__}.{RegisteredRegressionJob.__name__}',
                {'value': 'safe'},
            )
        )

        self.assertIsInstance(job, RegisteredRegressionJob)

    def test_legacy_and_v1_preserve_registered_class_allow_list(self) -> None:
        for schema_version in (None, 'routemq.job.v1'):
            with self.subTest(schema_version=schema_version):
                registered_payload = {
                    'class': f'{RegisteredRegressionJob.__module__}.{RegisteredRegressionJob.__name__}',
                    'data': {},
                }
                unregistered_payload = {
                    'class': f'{UnregisteredRegressionJob.__module__}.{UnregisteredRegressionJob.__name__}',
                    'data': {},
                }
                if schema_version is not None:
                    registered_payload['schema_version'] = schema_version
                    unregistered_payload['schema_version'] = schema_version

                Job.register(RegisteredRegressionJob)

                self.assertIsInstance(Job.unserialize(json.dumps(registered_payload)), RegisteredRegressionJob)
                with self.assertRaisesRegex(
                    ValueError,
                    'Refusing to load unregistered job class: .*Decorate the class with @Job.register',
                ):
                    Job.unserialize(json.dumps(unregistered_payload))

    def test_unregistered_job_class_is_rejected_before_import(self) -> None:
        """Unregistered classes raise the documented allow-list error."""
        payload = self.make_payload('builtins.eval')

        with self.assertRaisesRegex(ValueError, 'unregistered job class: builtins.eval'):
            Job.unserialize(payload)

    def test_registration_is_required_before_deserialization_succeeds(self) -> None:
        """Registration is required before a concrete Job subclass can be restored."""
        payload = self.make_payload(f'{UnregisteredRegressionJob.__module__}.{UnregisteredRegressionJob.__name__}')

        with self.assertRaisesRegex(ValueError, 'Decorate the class with @Job.register'):
            Job.unserialize(payload)

    def test_unknown_explicit_version_is_rejected_before_allow_list_and_import(self) -> None:
        payload = json.dumps(
            {
                'schema_version': 'routemq.job.v2',
                'class': 'builtins.eval',
                'data': {},
            }
        )

        for allowlist_disabled, environment in (
            (False, {}),
            (True, {'ROUTEMQ_JOB_ALLOWLIST_DISABLED': '1'}),
        ):
            with self.subTest(allowlist_disabled=allowlist_disabled):
                with patch.dict('os.environ', environment, clear=True):
                    with patch('builtins.__import__') as import_mock:
                        with self.assertRaises(ValueError) as raised:
                            Job.unserialize(payload)

                self.assertEqual(
                    str(raised.exception),
                    'Unsupported RouteMQ job schema version: routemq.job.v2',
                )
                import_mock.assert_not_called()

    def test_explicit_null_version_is_not_legacy(self) -> None:
        payload = json.dumps(
            {
                'schema_version': None,
                'class': 'builtins.eval',
                'data': {},
            }
        )

        with self.assertRaises(ValueError) as raised:
            Job.unserialize(payload)

        self.assertEqual(str(raised.exception), 'Unsupported RouteMQ job schema version: None')

    def test_malformed_payloads_raise_instead_of_falling_back(self) -> None:
        """Malformed payloads raise parsing or contract errors without fallback import."""
        malformed_payloads = [
            '{}',
            json.dumps({'data': {}}),
            json.dumps({'class': None, 'data': {}}),
            json.dumps({'class': '', 'data': {}}),
            json.dumps({'class': 123, 'data': {}}),
            'not-json',
        ]

        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises((KeyError, TypeError, ValueError, json.JSONDecodeError)):
                    Job.unserialize(payload)

    def test_dotted_path_traversal_is_rejected(self) -> None:
        """Dotted-path traversal cannot bypass the allow-list."""
        payload = self.make_payload('routemq..job.Job')

        with self.assertRaisesRegex(ValueError, 'unregistered job class: routemq..job.Job'):
            Job.unserialize(payload)

    def test_slash_path_traversal_is_rejected(self) -> None:
        """Slash path traversal cannot bypass the allow-list."""
        payload = self.make_payload('routemq/job.Job')

        with self.assertRaisesRegex(ValueError, 'unregistered job class: routemq/job.Job'):
            Job.unserialize(payload)

    def test_leading_dot_path_is_rejected(self) -> None:
        """Leading-dot class paths cannot bypass the allow-list."""
        payload = self.make_payload('.routemq.job.Job')

        with self.assertRaisesRegex(ValueError, 'unregistered job class: \\.routemq\\.job\\.Job'):
            Job.unserialize(payload)

    def test_case_variation_is_rejected(self) -> None:
        """Case-varied class paths do not match registered allow-list entries."""
        Job.register(RegisteredRegressionJob)
        payload = self.make_payload(f'{RegisteredRegressionJob.__module__.upper()}.{RegisteredRegressionJob.__name__}')

        with self.assertRaisesRegex(ValueError, 'unregistered job class'):
            Job.unserialize(payload)

    def test_whitespace_padded_class_name_is_rejected(self) -> None:
        """Whitespace-padded class paths do not match registered allow-list entries."""
        Job.register(RegisteredRegressionJob)
        payload = self.make_payload(f' {RegisteredRegressionJob.__module__}.{RegisteredRegressionJob.__name__} ')

        with self.assertRaisesRegex(ValueError, 'unregistered job class'):
            Job.unserialize(payload)

    def test_very_long_class_name_is_rejected(self) -> None:
        """Very long class paths cannot bypass the allow-list."""
        payload = self.make_payload(f'routemq.job.{"A" * 4096}')

        with self.assertRaisesRegex(ValueError, 'unregistered job class'):
            Job.unserialize(payload)

    def test_payload_data_cannot_register_future_allowed_classes(self) -> None:
        """Payload attributes cannot mutate the allow-list during restoration."""
        Job.register(RegisteredRegressionJob)
        injected_class = f'{UnregisteredRegressionJob.__module__}.{UnregisteredRegressionJob.__name__}'
        payload = self.make_payload(
            f'{RegisteredRegressionJob.__module__}.{RegisteredRegressionJob.__name__}',
            {'_allowed_classes': [injected_class]},
        )

        Job.unserialize(payload)

        self.assertNotIn(injected_class, Job._allowed_classes)

    def test_allow_list_disabled_env_restores_migration_behavior(self) -> None:
        """The migration env var is the only route that bypasses registration."""
        payload = self.make_payload(f'{UnregisteredRegressionJob.__module__}.{UnregisteredRegressionJob.__name__}')

        with patch.dict('os.environ', {'ROUTEMQ_JOB_ALLOWLIST_DISABLED': '1'}):
            job = Job.unserialize(payload)

        self.assertIsInstance(job, UnregisteredRegressionJob)


if __name__ == '__main__':
    unittest.main()
