"""Optional time-series database integration. Internal/unstable driver contract; see ADR-0010."""

from routemq.tsdb.tsdb_driver import TSDBDriver, TSDBSchemaError

__all__ = ['TSDBDriver', 'TSDBSchemaError']
