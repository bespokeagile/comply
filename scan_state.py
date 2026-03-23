"""In-memory scan state management for the web server."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ScanState:
    id: str
    url: str
    framework: str
    depth: str
    status: str = "pending"          # pending, cloning, scanning, building, evaluating, complete, error
    progress_step: str = ""
    progress_detail: str = ""
    report: Optional[dict] = None
    error: Optional[str] = None
    created_at: str = ""
    completed_at: str = ""
    output_dir: Optional[str] = None
    narration: Optional[str] = None
    narration_cost: Optional[dict] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


_lock = threading.Lock()
_scans: dict = {}  # id -> ScanState


def create_scan(url: str, framework: str, depth: str, output_dir: Optional[str] = None) -> ScanState:
    scan = ScanState(
        id=uuid.uuid4().hex[:12],
        url=url,
        framework=framework,
        depth=depth,
        output_dir=output_dir,
    )
    with _lock:
        _scans[scan.id] = scan
    return scan


def get_scan(scan_id: str) -> Optional[ScanState]:
    with _lock:
        return _scans.get(scan_id)


def update_scan(scan_id: str, **kwargs) -> Optional[ScanState]:
    with _lock:
        scan = _scans.get(scan_id)
        if scan is None:
            return None
        for key, val in kwargs.items():
            if hasattr(scan, key):
                setattr(scan, key, val)
        return scan


def list_scans() -> list:
    with _lock:
        return [
            {
                "id": s.id,
                "url": s.url,
                "framework": s.framework,
                "status": s.status,
                "created_at": s.created_at,
            }
            for s in sorted(_scans.values(), key=lambda s: s.created_at, reverse=True)
        ]
