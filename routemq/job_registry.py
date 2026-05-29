import importlib
import logging
import pkgutil


class JobRegistry:
    """Discover job modules so @Job.register decorators are executed."""

    def __init__(self, job_directory: str = 'app.jobs'):
        self.job_directory = job_directory
        self.logger = logging.getLogger('RouteMQ.JobRegistry')

    def discover_and_register_jobs(self) -> list[str]:
        """Import public job modules from the configured package."""
        try:
            jobs_package = importlib.import_module(self.job_directory)
            package_path = jobs_package.__path__
        except ImportError as e:
            self.logger.info(f"Could not import job directory '{self.job_directory}': {e}")
            return []
        except AttributeError:
            self.logger.warning(f"Job directory '{self.job_directory}' is not a package")
            return []

        job_modules = [
            f'{self.job_directory}.{name}'
            for _, name, ispkg in pkgutil.iter_modules(package_path)
            if not ispkg and not name.startswith('_')
        ]

        loaded_modules: list[str] = []
        for module_name in job_modules:
            try:
                importlib.import_module(module_name)
                loaded_modules.append(module_name)
            except ImportError as e:
                self.logger.error(f"Could not import job module '{module_name}': {e}")
            except Exception as e:
                self.logger.error(f"Error loading job module '{module_name}': {e}")

        self.logger.info(f'Discovered job modules: {loaded_modules}')
        return loaded_modules


def discover_and_register_jobs(job_directory: str = 'app.jobs') -> list[str]:
    """Convenience function to import job modules and execute registrations."""
    return JobRegistry(job_directory).discover_and_register_jobs()
