import json
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from core.job import Job


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
        return json.dumps({"class": class_name, "data": dict(data or {})})

    def test_registered_job_class_deserializes(self) -> None:
        """Allow-listed job class deserializes to the expected Job subclass."""
        Job.register(RegisteredRegressionJob)

        job = Job.unserialize(
            self.make_payload(
                f"{RegisteredRegressionJob.__module__}.{RegisteredRegressionJob.__name__}",
                {"value": "safe"},
            )
        )

        self.assertIsInstance(job, RegisteredRegressionJob)

    def test_unregistered_job_class_is_rejected_before_import(self) -> None:
        """Unregistered classes raise the documented allow-list error."""
        payload = self.make_payload("builtins.eval")

        with self.assertRaisesRegex(ValueError, "unregistered job class: builtins.eval"):
            Job.unserialize(payload)

    def test_registration_is_required_before_deserialization_succeeds(self) -> None:
        """Registration is required before a concrete Job subclass can be restored."""
        payload = self.make_payload(
            f"{UnregisteredRegressionJob.__module__}.{UnregisteredRegressionJob.__name__}"
        )

        with self.assertRaisesRegex(ValueError, "Decorate the class with @Job.register"):
            Job.unserialize(payload)

    def test_malformed_payloads_raise_instead_of_falling_back(self) -> None:
        """Malformed payloads raise parsing or contract errors without fallback import."""
        malformed_payloads = [
            "{}",
            json.dumps({"data": {}}),
            json.dumps({"class": None, "data": {}}),
            json.dumps({"class": "", "data": {}}),
            json.dumps({"class": 123, "data": {}}),
            "not-json",
        ]

        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises((KeyError, TypeError, ValueError, json.JSONDecodeError)):
                    Job.unserialize(payload)

    def test_dotted_path_traversal_is_rejected(self) -> None:
        """Dotted-path traversal cannot bypass the allow-list."""
        payload = self.make_payload("core..job.Job")

        with self.assertRaisesRegex(ValueError, "unregistered job class: core..job.Job"):
            Job.unserialize(payload)

    def test_slash_path_traversal_is_rejected(self) -> None:
        """Slash path traversal cannot bypass the allow-list."""
        payload = self.make_payload("core/job.Job")

        with self.assertRaisesRegex(ValueError, "unregistered job class: core/job.Job"):
            Job.unserialize(payload)

    def test_leading_dot_path_is_rejected(self) -> None:
        """Leading-dot class paths cannot bypass the allow-list."""
        payload = self.make_payload(".core.job.Job")

        with self.assertRaisesRegex(ValueError, "unregistered job class: \\.core\\.job\\.Job"):
            Job.unserialize(payload)

    def test_case_variation_is_rejected(self) -> None:
        """Case-varied class paths do not match registered allow-list entries."""
        Job.register(RegisteredRegressionJob)
        payload = self.make_payload(
            f"{RegisteredRegressionJob.__module__.upper()}.{RegisteredRegressionJob.__name__}"
        )

        with self.assertRaisesRegex(ValueError, "unregistered job class"):
            Job.unserialize(payload)

    def test_whitespace_padded_class_name_is_rejected(self) -> None:
        """Whitespace-padded class paths do not match registered allow-list entries."""
        Job.register(RegisteredRegressionJob)
        payload = self.make_payload(
            f" {RegisteredRegressionJob.__module__}.{RegisteredRegressionJob.__name__} "
        )

        with self.assertRaisesRegex(ValueError, "unregistered job class"):
            Job.unserialize(payload)

    def test_very_long_class_name_is_rejected(self) -> None:
        """Very long class paths cannot bypass the allow-list."""
        payload = self.make_payload(f"core.job.{'A' * 4096}")

        with self.assertRaisesRegex(ValueError, "unregistered job class"):
            Job.unserialize(payload)

    def test_payload_data_cannot_register_future_allowed_classes(self) -> None:
        """Payload attributes cannot mutate the allow-list during restoration."""
        Job.register(RegisteredRegressionJob)
        injected_class = f"{UnregisteredRegressionJob.__module__}.{UnregisteredRegressionJob.__name__}"
        payload = self.make_payload(
            f"{RegisteredRegressionJob.__module__}.{RegisteredRegressionJob.__name__}",
            {"_allowed_classes": [injected_class]},
        )

        Job.unserialize(payload)

        self.assertNotIn(injected_class, Job._allowed_classes)

    def test_allow_list_disabled_env_restores_migration_behavior(self) -> None:
        """The migration env var is the only route that bypasses registration."""
        payload = self.make_payload(
            f"{UnregisteredRegressionJob.__module__}.{UnregisteredRegressionJob.__name__}"
        )

        with patch.dict("os.environ", {"ROUTEMQ_JOB_ALLOWLIST_DISABLED": "1"}):
            job = Job.unserialize(payload)

        self.assertIsInstance(job, UnregisteredRegressionJob)


if __name__ == "__main__":
    unittest.main()
