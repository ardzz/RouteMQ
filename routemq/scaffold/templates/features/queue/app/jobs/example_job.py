from routemq.job import Job


class ExampleJob(Job):
    """Example background job."""

    queue = 'default'
    max_tries = 3

    async def handle(self):
        print('Processing ExampleJob')
