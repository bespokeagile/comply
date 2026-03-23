"""Generic JSONL file adapter — escape hatch for any system.

Reads JSON-lines files where each line maps to a NormalizedTrafficRecord.
Supports glob patterns for multi-file ingestion.

Configure via ``~/.comply/config.yaml``:

.. code-block:: yaml

    adapters:
      file:
        paths:
          - /var/log/ai-gateway/*.jsonl
          - ./audit-export.jsonl

Each JSON line must have at least ``record_id`` and ``tool_name``.
"""
from __future__ import annotations

import glob
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from comply.adapters.base import AuditLogAdapter, NormalizedTrafficRecord

log = logging.getLogger(__name__)


class FileAdapter(AuditLogAdapter):
    """Adapter that reads NormalizedTrafficRecords from JSONL files."""

    def __init__(self):
        self._paths: List[str] = []
        self._last_fetch: str = ""

    def configure(self, config: Dict[str, Any]) -> None:
        raw = config.get("paths", [])
        if isinstance(raw, str):
            raw = [raw]
        self._paths = raw

    def test_connection(self) -> bool:
        """Check that at least one configured path resolves to a file."""
        for pattern in self._paths:
            expanded = glob.glob(os.path.expanduser(pattern))
            if expanded:
                return True
        return bool(self._paths)

    def fetch_records(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 1000,
    ) -> List[NormalizedTrafficRecord]:
        records = []
        seen_files = set()

        for pattern in self._paths:
            for path in glob.glob(os.path.expanduser(pattern)):
                if path in seen_files:
                    continue
                seen_files.add(path)

                try:
                    with open(path) as f:
                        for line_no, line in enumerate(f, 1):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                d = json.loads(line)
                            except json.JSONDecodeError:
                                log.warning("Bad JSON at %s:%d", path, line_no)
                                continue

                            # Ensure source_adapter is set
                            d.setdefault("source_adapter", "file")
                            d.setdefault("action", "call")
                            d.setdefault("timestamp", "")

                            # Time filter
                            ts = d.get("timestamp", "")
                            if since and ts and ts < since:
                                continue
                            if until and ts and ts > until:
                                continue

                            records.append(NormalizedTrafficRecord.from_dict(d))
                            if len(records) >= limit:
                                break
                except Exception as exc:
                    log.warning("Failed to read %s: %s", path, exc)

                if len(records) >= limit:
                    break
            if len(records) >= limit:
                break

        self._last_fetch = datetime.now(timezone.utc).isoformat()
        return records

    def get_adapter_status(self) -> Dict[str, Any]:
        file_count = 0
        for pattern in self._paths:
            file_count += len(glob.glob(os.path.expanduser(pattern)))
        return {
            "name": "file",
            "connected": file_count > 0,
            "last_fetch": self._last_fetch,
            "patterns": self._paths,
            "resolved_files": file_count,
        }
