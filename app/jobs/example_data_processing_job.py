import asyncio
import logging
from core.job import Job

logger = logging.getLogger("RouteMQ.Jobs.ProcessDataJob")


class ProcessDataJob(Job):
    """
    Example job for processing data in the background.

    This demonstrates a job that processes sensor data from IoT devices.

    Usage:
        from app.jobs.example_data_processing_job import ProcessDataJob
        from core.queue.queue_manager import dispatch

        # Dispatch the job
        job = ProcessDataJob()
        job.device_id = "sensor-001"
        job.sensor_data = {"temperature": 25.5, "humidity": 60}
        await dispatch(job)
    """

    # Configure job properties
    max_tries = 5
    timeout = 120  # Longer timeout for data processing
    retry_after = 5
    queue = "data-processing"

    def __init__(self):
        super().__init__()
        self.device_id = None
        self.sensor_data = None

    async def handle(self) -> None:
        """
        Execute the job - process sensor data.
        """
        logger.info(f"Processing data from device {self.device_id}")
        logger.info(f"Sensor data: {self.sensor_data}")

        # Simulate data processing
        await asyncio.sleep(3)

        # Example: Calculate statistics
        if isinstance(self.sensor_data, dict):
            temperature = self.sensor_data.get("temperature")
            humidity = self.sensor_data.get("humidity")

            if temperature and temperature > 30:
                logger.warning(f"High temperature detected: {temperature}°C")

            if humidity and humidity > 80:
                logger.warning(f"High humidity detected: {humidity}%")

        # In a real application, you might:
        # - Store processed data in a database
        # - Calculate aggregations and statistics
        # - Trigger alerts if thresholds are exceeded
        # - Send data to analytics services

        logger.info(f"Successfully processed data from device {self.device_id}")

    async def failed(self, exception: Exception) -> None:
        """
        Handle permanent job failure.
        """
        logger.error(
            f"Failed to process data from device {self.device_id} "
            f"after {self.max_tries} attempts"
        )
        logger.error(f"Error: {str(exception)}")
