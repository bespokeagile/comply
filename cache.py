"""Scan model cache — avoids re-scanning when only the framework changes.

Keyed by hash(repo_path, scan_depth, commit_sha). Stored in ~/.comply/cache/.
LRU eviction (max 10 entries), 24h TTL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

_CACHE_DIR = os.path.expanduser("~/.comply/cache")
_MAX_ENTRIES = 10
_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _cache_key(repo_path: str, scan_depth: str, commit_sha: str) -> str:
    """Generate a deterministic cache key."""
    data = f"{os.path.abspath(repo_path)}|{scan_depth}|{commit_sha}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _entry_path(key: str) -> str:
    return os.path.join(_CACHE_DIR, f"{key}.json")


def get_cached_project(repo_path: str, scan_depth: str, commit_sha: str) -> Optional[dict]:
    """Return cached scan+model result if available and fresh. None otherwise."""
    if not commit_sha:
        return None  # Can't cache without a commit SHA

    key = _cache_key(repo_path, scan_depth, commit_sha)
    path = _entry_path(key)

    if not os.path.isfile(path):
        return None

    try:
        with open(path) as f:
            entry = json.load(f)

        # Check TTL
        cached_at = entry.get("cached_at", 0)
        if time.time() - cached_at > _TTL_SECONDS:
            log.debug("Cache entry %s expired", key)
            os.unlink(path)
            return None

        # Touch for LRU
        os.utime(path, None)

        log.info("Cache hit for %s (depth=%s, sha=%s)", repo_path, scan_depth, commit_sha[:8])
        return entry.get("data")

    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Cache read error for %s: %s", key, exc)
        return None


def save_to_cache(repo_path: str, scan_depth: str, commit_sha: str, data: dict):
    """Save scan+model result to cache."""
    if not commit_sha:
        return  # Don't cache without a commit SHA

    os.makedirs(_CACHE_DIR, exist_ok=True)

    key = _cache_key(repo_path, scan_depth, commit_sha)
    entry = {
        "cached_at": time.time(),
        "repo_path": os.path.abspath(repo_path),
        "scan_depth": scan_depth,
        "commit_sha": commit_sha,
        "data": data,
    }

    try:
        with open(_entry_path(key), "w") as f:
            json.dump(entry, f, default=str)
        log.debug("Cached scan model as %s", key)
    except OSError as exc:
        log.warning("Cache write error: %s", exc)
        return

    _evict_lru()


def invalidate_cache(repo_path: str, scan_depth: str, commit_sha: str):
    """Remove a specific cache entry."""
    key = _cache_key(repo_path, scan_depth, commit_sha)
    path = _entry_path(key)
    if os.path.isfile(path):
        os.unlink(path)


def clear_cache():
    """Remove all cache entries."""
    if not os.path.isdir(_CACHE_DIR):
        return 0
    count = 0
    for name in os.listdir(_CACHE_DIR):
        if name.endswith(".json"):
            try:
                os.unlink(os.path.join(_CACHE_DIR, name))
                count += 1
            except OSError:
                pass
    return count


def get_cache_stats() -> dict:
    """Return cache stats: entry count, total size, oldest/newest timestamps."""
    if not os.path.isdir(_CACHE_DIR):
        return {"entries": 0, "total_bytes": 0, "oldest": None, "newest": None}

    entries = []
    total_bytes = 0
    for name in os.listdir(_CACHE_DIR):
        if name.endswith(".json"):
            path = os.path.join(_CACHE_DIR, name)
            try:
                stat = os.stat(path)
                entries.append(stat.st_mtime)
                total_bytes += stat.st_size
            except OSError:
                pass

    if not entries:
        return {"entries": 0, "total_bytes": 0, "oldest": None, "newest": None}

    entries.sort()
    return {
        "entries": len(entries),
        "total_bytes": total_bytes,
        "oldest": entries[0],
        "newest": entries[-1],
        "max_entries": _MAX_ENTRIES,
        "ttl_hours": _TTL_SECONDS / 3600,
    }


def _evict_lru():
    """Evict oldest entries if over the max count."""
    if not os.path.isdir(_CACHE_DIR):
        return

    files = []
    for name in os.listdir(_CACHE_DIR):
        if name.endswith(".json"):
            path = os.path.join(_CACHE_DIR, name)
            try:
                files.append((os.stat(path).st_mtime, path))
            except OSError:
                pass

    if len(files) <= _MAX_ENTRIES:
        return

    # Sort by mtime ascending (oldest first), delete extras
    files.sort()
    for _, path in files[: len(files) - _MAX_ENTRIES]:
        try:
            os.unlink(path)
            log.debug("Evicted cache entry: %s", path)
        except OSError:
            pass
