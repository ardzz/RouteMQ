from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

from routemq.telemetry.types import TelemetryPoint


@dataclass(frozen=True, slots=True)
class WriteFailure:
    index: int
    point: TelemetryPoint
    error: str
    retriable: bool = True


@dataclass(frozen=True, slots=True)
class WriteResult:
    accepted: int = 0
    written: int = 0
    failures: tuple[WriteFailure, ...] = ()

    @property
    def success(self) -> bool:
        return not self.failures and self.accepted == self.written


@dataclass(frozen=True, slots=True)
class SchemaValidationIssue:
    message: str
    backend: str | None = None
    object_name: str | None = None
    severity: str = 'error'


@dataclass(frozen=True, slots=True)
class SchemaValidationResult:
    ok: bool = True
    issues: tuple[SchemaValidationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class TelemetryHealthStatus:
    ok: bool
    backend: str
    message: str = ''


class TelemetryAdapter(ABC):
    @abstractmethod
    async def write_many(self, points: Sequence[TelemetryPoint]) -> WriteResult:
        pass  # pragma: no cover - abstract contract

    @abstractmethod
    async def validate_schema(self) -> SchemaValidationResult:
        pass  # pragma: no cover - abstract contract

    @abstractmethod
    async def health_check(self) -> TelemetryHealthStatus:
        pass  # pragma: no cover - abstract contract

    @abstractmethod
    async def close(self) -> None:
        pass  # pragma: no cover - abstract contract


@dataclass(slots=True)
class NoopTelemetryAdapter(TelemetryAdapter):
    backend: str = 'noop'

    async def write_many(self, points: Sequence[TelemetryPoint]) -> WriteResult:
        return WriteResult(accepted=len(points), written=len(points))

    async def validate_schema(self) -> SchemaValidationResult:
        return SchemaValidationResult()

    async def health_check(self) -> TelemetryHealthStatus:
        return TelemetryHealthStatus(ok=True, backend=self.backend)

    async def close(self) -> None:
        return None


@dataclass(slots=True)
class InMemoryTelemetryAdapter(TelemetryAdapter):
    backend: str = 'memory'
    points: list[TelemetryPoint] = field(default_factory=list)

    async def write_many(self, points: Sequence[TelemetryPoint]) -> WriteResult:
        stored = list(points)
        self.points.extend(stored)
        return WriteResult(accepted=len(stored), written=len(stored))

    async def validate_schema(self) -> SchemaValidationResult:
        return SchemaValidationResult()

    async def health_check(self) -> TelemetryHealthStatus:
        return TelemetryHealthStatus(ok=True, backend=self.backend)

    async def close(self) -> None:
        return None
