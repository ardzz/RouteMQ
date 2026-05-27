import inspect
import json
import unittest
from collections.abc import MutableSequence
from typing import Any, cast

from routemq.job import Job


class SerializableJob(Job):
    queue = 'serialization'

    def __init__(self) -> None:
        super().__init__()
        self.name = 'alpha'
        self.payload = {'count': 1}

    async def handle(self) -> None:
        return None


class OverrideDefaultsJob(Job):
    max_tries = 5
    queue = 'critical'
    retry_after = 30

    async def handle(self) -> None:
        return None


class MutableStateJob(Job):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[str] = []

    async def handle(self) -> None:
        return None


class EmptyQueueJob(Job):
    queue = ''

    async def handle(self) -> None:
        return None


class ZeroMaxTriesJob(Job):
    max_tries = 0

    async def handle(self) -> None:
        return None


class NegativeMaxTriesJob(Job):
    max_tries = -1

    async def handle(self) -> None:
        return None


class MissingHandleJob(Job):
    pass


class TestJobDefaults(unittest.TestCase):
    def test_base_class_defaults_are_stable(self) -> None:
        """Base Job defaults remain the queue worker contract."""
        self.assertEqual((Job.max_tries, Job.queue, Job.retry_after), (3, 'default', 0))

    def test_subclass_defaults_override_base_values(self) -> None:
        """Subclass class attributes override base dispatch defaults."""
        self.assertEqual(
            (OverrideDefaultsJob.max_tries, OverrideDefaultsJob.queue, OverrideDefaultsJob.retry_after),
            (5, 'critical', 30),
        )

    def test_constructor_initializes_runtime_state(self) -> None:
        """No-argument construction initializes queue runtime metadata."""
        job = SerializableJob()

        self.assertEqual((job.job_id, job.attempts), (None, 0))

    def test_constructor_rejects_positional_payload(self) -> None:
        """Base constructor does not accept positional payload data."""
        job_class = cast(Any, SerializableJob)

        with self.assertRaises(TypeError):
            job_class({'name': 'alpha'})

    def test_constructor_rejects_keyword_payload(self) -> None:
        """Base constructor does not accept keyword payload data."""
        job_class = cast(Any, SerializableJob)

        with self.assertRaises(TypeError):
            job_class(name='alpha')


class TestJobAbstractContract(unittest.TestCase):
    def test_base_job_cannot_be_instantiated(self) -> None:
        """Abstract handle prevents direct base Job instantiation."""
        job_class = cast(Any, Job)

        with self.assertRaises(TypeError):
            job_class()

    def test_subclass_without_handle_cannot_be_instantiated(self) -> None:
        """Subclasses must implement handle before instantiation."""
        job_class = cast(Any, MissingHandleJob)

        with self.assertRaises(TypeError):
            job_class()

    def test_handle_contract_is_async(self) -> None:
        """Concrete handle implementations remain coroutine functions."""
        self.assertTrue(inspect.iscoroutinefunction(SerializableJob.handle))


class TestJobHandleExecution(unittest.IsolatedAsyncioTestCase):
    async def test_concrete_handle_is_awaitable(self) -> None:
        """Concrete async handle can be awaited by queue workers."""
        await SerializableJob().handle()

        self.assertTrue(True)


class TestJobSerialization(unittest.TestCase):
    def setUp(self) -> None:
        self._allowed_classes = set(Job._allowed_classes)
        Job._allowed_classes.clear()

    def tearDown(self) -> None:
        Job._allowed_classes.clear()
        Job._allowed_classes.update(self._allowed_classes)

    def test_serialize_round_trip_restores_equivalent_instance(self) -> None:
        """Serialized job payload restores equivalent registered instance data."""
        Job.register(SerializableJob)

        restored = Job.unserialize(SerializableJob().serialize())

        self.assertIsInstance(restored, SerializableJob)
        restored_job = cast(SerializableJob, restored)
        self.assertEqual(
            (restored_job.name, restored_job.payload, restored_job.queue), ('alpha', {'count': 1}, 'serialization')
        )

    def test_empty_queue_name_survives_serialization(self) -> None:
        """Empty queue class attributes are preserved, not defaulted."""
        Job.register(EmptyQueueJob)

        restored = Job.unserialize(EmptyQueueJob().serialize())

        self.assertEqual(restored.queue, '')

    def test_zero_max_tries_survives_serialization(self) -> None:
        """Zero max_tries is preserved for edge-case retry policy tests."""
        Job.register(ZeroMaxTriesJob)

        restored = Job.unserialize(ZeroMaxTriesJob().serialize())

        self.assertEqual(restored.max_tries, 0)

    def test_negative_max_tries_survives_serialization(self) -> None:
        """Negative max_tries is preserved without validation in Job."""
        Job.register(NegativeMaxTriesJob)

        restored = Job.unserialize(NegativeMaxTriesJob().serialize())

        self.assertEqual(restored.max_tries, -1)

    def test_get_data_excludes_runtime_fields(self) -> None:
        """Serializable data excludes queue runtime metadata."""
        job = SerializableJob()
        job.job_id = 7
        job.attempts = 2

        self.assertEqual(job.get_data(), {'name': 'alpha', 'payload': {'count': 1}})

    def test_serialize_emits_expected_metadata(self) -> None:
        """Serialized JSON includes dispatch metadata beside job data."""
        data: dict[str, Any] = json.loads(SerializableJob().serialize())

        self.assertEqual(
            (data['max_tries'], data['timeout'], data['retry_after'], data['queue']), (3, 60, 0, 'serialization')
        )


class TestJobInstanceState(unittest.TestCase):
    def test_mutable_instance_state_is_not_shared(self) -> None:
        """Mutable payload belongs to each instance, not the Job class."""
        first = MutableStateJob()
        second = MutableStateJob()
        first.items.append('first')

        self.assertEqual(second.items, [])

    def test_mutable_state_lives_on_instance_dict(self) -> None:
        """Mutable state is stored on the instance where get_data can serialize it."""
        job = MutableStateJob()

        self.assertIsInstance(job.__dict__['items'], MutableSequence)


class TestJobRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self._allowed_classes = set(Job._allowed_classes)
        Job._allowed_classes.clear()

    def tearDown(self) -> None:
        Job._allowed_classes.clear()
        Job._allowed_classes.update(self._allowed_classes)

    def test_register_returns_original_class(self) -> None:
        """Decorator-style registration preserves the original class object."""
        self.assertIs(Job.register(SerializableJob), SerializableJob)

    def test_register_adds_fully_qualified_class_name(self) -> None:
        """Registry stores the import path used by unserialize lookup."""
        Job.register(SerializableJob)

        self.assertIn(f'{__name__}.SerializableJob', Job._allowed_classes)

    def test_registered_class_path_can_be_looked_up(self) -> None:
        """Allow-list membership is the registry lookup mechanism."""
        Job.register(SerializableJob)
        class_path = f'{SerializableJob.__module__}.{SerializableJob.__name__}'

        self.assertTrue(class_path in Job._allowed_classes)

    def test_double_registration_is_idempotent(self) -> None:
        """Registering the same class twice keeps one allow-list entry."""
        Job.register(SerializableJob)
        Job.register(SerializableJob)

        self.assertEqual(len(Job._allowed_classes), 1)


if __name__ == '__main__':
    unittest.main()
