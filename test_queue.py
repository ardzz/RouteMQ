#!/usr/bin/env python3
"""
Quick test script to verify the queue system works correctly.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from core.job import Job
from core.queue.queue_manager import dispatch, queue
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class TestJob(Job):
    """Simple test job."""

    max_tries = 2
    timeout = 10
    queue = "test"

    def __init__(self):
        super().__init__()
        self.test_data = None

    async def handle(self):
        logger.info(f"Processing TestJob with data: {self.test_data}")
        await asyncio.sleep(1)
        logger.info("TestJob completed successfully!")

    async def failed(self, exception: Exception):
        logger.error(f"TestJob failed: {exception}")


async def test_job_serialization():
    """Test job serialization and deserialization."""
    logger.info("Testing job serialization...")

    # Create a job
    job = TestJob()
    job.test_data = {"message": "Hello, Queue!", "number": 42}

    # Serialize
    payload = job.serialize()
    logger.info(f"Serialized payload: {payload}")

    # Deserialize
    restored_job = Job.unserialize(payload)
    logger.info(f"Restored job: {restored_job}")
    logger.info(f"Restored data: {restored_job.test_data}")

    assert restored_job.test_data == job.test_data
    logger.info("✅ Serialization test passed!")


async def test_dispatch():
    """Test dispatching a job (without actually processing it)."""
    logger.info("\nTesting job dispatch...")

    # Note: This requires Redis or MySQL to be enabled
    # For a basic test, we'll just verify the job can be created and serialized

    job = TestJob()
    job.test_data = {"test": "dispatch"}

    logger.info("Created test job successfully")
    logger.info("✅ Job creation test passed!")

    # To actually test dispatch, you would need:
    # await dispatch(job)
    # But this requires a running Redis/MySQL instance


async def main():
    """Run all tests."""
    logger.info("Starting queue system tests...")
    logger.info("=" * 50)

    load_dotenv()

    try:
        # Test 1: Serialization
        await test_job_serialization()

        # Test 2: Dispatch
        await test_dispatch()

        logger.info("\n" + "=" * 50)
        logger.info("✅ All tests passed!")
        logger.info("\nTo test the full queue system:")
        logger.info("1. Enable Redis or MySQL in your .env file")
        logger.info("2. Run: python main.py --queue-work --queue test")
        logger.info("3. In another terminal, dispatch a job using the example jobs")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
