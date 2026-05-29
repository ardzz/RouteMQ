"""Abstract TSDB driver contract. Internal and unstable until ADR-0010 registry extraction."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any


class TSDBSchemaError(RuntimeError):
    """Raised when a target measurement is missing or its columns do not match expectations."""


class TSDBDriver(ABC):
    """Abstract base class for time-series database drivers.

    Implementations land MQTT telemetry into a backend such as ClickHouse. Reads are not
    unified; applications use the native ``client`` escape hatch for backend-specific queries.
    """

    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def ensure_schema(self, measurement: str, columns: Sequence[str]) -> None:
        """Validate that ``measurement`` exists and exposes ``columns``.

        Raises:
            TSDBSchemaError: if the table is missing or its column set does not match.
        """
        pass

    @abstractmethod
    async def write_points(self, measurement: str, rows: Sequence[Mapping[str, Any]]) -> None:
        """Buffer rows for a later batched insert into ``measurement``."""
        pass

    @abstractmethod
    async def flush(self) -> None:
        """Drain the buffer with a single batched insert per measurement."""
        pass

    @abstractmethod
    async def health(self) -> bool:
        pass

    @property
    @abstractmethod
    def client(self) -> Any:
        """Native backend client for app-written queries (escape hatch)."""
        pass
