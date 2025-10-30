import asyncio
import logging
from datetime import datetime
from core.job import Job

logger = logging.getLogger("RouteMQ.Jobs.GenerateReportJob")


class GenerateReportJob(Job):
    """
    Example job for generating reports in the background.

    This demonstrates a long-running job that generates reports
    and demonstrates delayed job execution.

    Usage:
        from app.jobs.example_report_job import GenerateReportJob
        from core.queue.queue_manager import queue

        # Dispatch the job immediately
        job = GenerateReportJob()
        job.report_type = "daily"
        job.user_id = 123
        await queue.push(job)

        # Or schedule it to run after a delay (in seconds)
        await queue.later(3600, job)  # Run after 1 hour
    """

    # Configure job properties
    max_tries = 2
    timeout = 300  # 5 minutes for report generation
    retry_after = 60  # Retry after 1 minute
    queue = "reports"

    def __init__(self):
        super().__init__()
        self.report_type = None
        self.user_id = None

    async def handle(self) -> None:
        """
        Execute the job - generate a report.
        """
        logger.info(f"Generating {self.report_type} report for user {self.user_id}")

        # Simulate report generation
        await asyncio.sleep(5)

        # In a real application, you might:
        # - Query database for report data
        # - Generate PDF or Excel file
        # - Upload to cloud storage
        # - Send email notification with download link
        # - Update user's report history

        report_file = f"{self.report_type}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        logger.info(f"Report generated successfully: {report_file}")
        logger.info(f"Report available for user {self.user_id}")

    async def failed(self, exception: Exception) -> None:
        """
        Handle permanent job failure.
        """
        logger.error(
            f"Failed to generate {self.report_type} report for user {self.user_id} "
            f"after {self.max_tries} attempts"
        )
        logger.error(f"Error: {str(exception)}")

        # In a real application, you might:
        # - Notify the user that report generation failed
        # - Log to monitoring service
        # - Create a support ticket
