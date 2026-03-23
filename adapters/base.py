"""Abstract base class for audit log adapters + normalized record format.

Every adapter ingests audit/traffic logs from an external system (API gateway,
MCP proxy, etc.) and normalises them into ``NormalizedTrafficRecord`` instances
that Comply can use for Layer 3 (AI agent governance) evidence.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class NormalizedTrafficRecord:
    """A single normalised audit/traffic event from any source."""

    record_id: str
    timestamp: str  # ISO-8601
    source_adapter: str
    tool_name: str
    caller_identity: str = ""
    action: str = "call"  # call | deny | error
    duration_ms: float = 0.0
    status: str = "ok"
    policy_matched: str = ""
    cost_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NormalizedTrafficRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


class AuditLogAdapter(ABC):
    """Abstract base for all audit log adapters.

    Concrete adapters must implement the four core methods below.
    Configuration is passed via ``configure()`` before any other call.
    """

    @abstractmethod
    def configure(self, config: Dict[str, Any]) -> None:
        """Apply adapter-specific configuration.

        Parameters
        ----------
        config : dict
            Adapter settings from ``~/.comply/config.yaml`` or inline.
        """
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify connectivity to the audit log source.

        Returns
        -------
        bool
            ``True`` if the adapter can reach its data source.
        """
        ...

    @abstractmethod
    def fetch_records(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 1000,
    ) -> List[NormalizedTrafficRecord]:
        """Pull normalised records from the external system.

        Parameters
        ----------
        since : str or None
            ISO-8601 lower bound (inclusive).
        until : str or None
            ISO-8601 upper bound (inclusive).
        limit : int
            Maximum records to return per call.

        Returns
        -------
        list of NormalizedTrafficRecord
        """
        ...

    @abstractmethod
    def get_adapter_status(self) -> Dict[str, Any]:
        """Return a status summary for this adapter.

        Returns
        -------
        dict
            Must include at least ``name``, ``connected`` (bool), and
            ``last_fetch`` (ISO-8601 or empty string).
        """
        ...
