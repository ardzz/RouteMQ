import asyncio
import logging
from core.job import Job

logger = logging.getLogger("RouteMQ.Jobs.SendEmailJob")


class SendEmailJob(Job):
    """
    Example job for sending emails in the background.

    Usage:
        from app.jobs.example_email_job import SendEmailJob
        from core.queue.queue_manager import dispatch

        # Dispatch the job
        job = SendEmailJob()
        job.to = "user@example.com"
        job.subject = "Welcome!"
        job.message = "Thank you for signing up."
        await dispatch(job)
    """

    # Configure job properties
    max_tries = 3
    timeout = 30
    retry_after = 10  # Retry after 10 seconds on failure
    queue = "emails"  # Use 'emails' queue instead of 'default'

    def __init__(self):
        super().__init__()
        self.to = None
        self.subject = None
        self.message = None

    async def handle(self) -> None:
        """
        Execute the job - send an email.
        In a real application, this would use an email service like SendGrid, AWS SES, etc.
        """
        logger.info(f"Sending email to {self.to}")
        logger.info(f"Subject: {self.subject}")
        logger.info(f"Message: {self.message}")

        # Simulate email sending (replace with actual email service)
        await asyncio.sleep(2)  # Simulate API call delay

        # Uncomment to test job failure and retry
        # if self.attempts == 1:
        #     raise Exception("Simulated email sending failure")

        logger.info(f"Email sent successfully to {self.to}")

    async def failed(self, exception: Exception) -> None:
        """
        Handle permanent job failure.
        This is called when the job exceeds max_tries.
        """
        logger.error(f"Failed to send email to {self.to} after {self.max_tries} attempts")
        logger.error(f"Error: {str(exception)}")

        # In a real application, you might:
        # - Log to a monitoring service
        # - Send alert to administrators
        # - Store failure in a database for manual review
