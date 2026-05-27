import unittest

from routemq.queue.queue_driver import QueueDriver


class _StubDriver(QueueDriver):
    async def push(self, payload, queue='default', delay=0):
        return await super().push(payload, queue, delay)

    async def pop(self, queue='default'):
        return await super().pop(queue)

    async def release(self, job_id, queue, delay=0):
        return await super().release(job_id, queue, delay)

    async def delete(self, job_id, queue):
        return await super().delete(job_id, queue)

    async def failed(self, connection, queue, payload, exception):
        return await super().failed(connection, queue, payload, exception)

    async def size(self, queue='default'):
        return await super().size(queue)


class QueueDriverAbstractContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_super_calls_return_none_for_all_methods(self) -> None:
        driver = _StubDriver()
        self.assertIsNone(await driver.push('payload'))
        self.assertIsNone(await driver.pop())
        self.assertIsNone(await driver.release('id', 'q'))
        self.assertIsNone(await driver.delete('id', 'q'))
        self.assertIsNone(await driver.failed('c', 'q', 'p', 'e'))
        self.assertIsNone(await driver.size())

    def test_direct_instantiation_raises_type_error(self) -> None:
        with self.assertRaises(TypeError):
            QueueDriver()  # type: ignore[abstract]


if __name__ == '__main__':
    unittest.main()
