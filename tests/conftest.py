"""Pytest fixtures for Comply snapshot testing.

Provides:
- Deterministic persona DB seeding via SeedContext
- TestClient fixtures per persona (no subprocess servers)
- Snapshot comparison utilities with --update-snapshots flag
"""
from __future__ import annotations

import json
import os
import threading

import pytest


# ---------------------------------------------------------------------------
# pytest CLI option
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots", action="store_true", default=False,
        help="Regenerate snapshot fixture files with current output",
    )


# ---------------------------------------------------------------------------
# Snapshot infrastructure
# ---------------------------------------------------------------------------
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "snapshots")


def assert_snapshot(actual, snapshot_name: str, *, update: bool = False):
    """Compare *actual* (dict or list) against a saved JSON snapshot.

    - First run or --update-snapshots: writes snapshot file.
    - Subsequent runs: asserts equality.
    """
    path = os.path.join(SNAPSHOT_DIR, f"{snapshot_name}.json")

    if update or not os.path.exists(path):
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(actual, f, indent=2, sort_keys=True)
            f.write("\n")
        return  # nothing to assert on first write

    with open(path) as f:
        expected = json.load(f)

    assert actual == expected, (
        f"Snapshot mismatch: {snapshot_name}\n"
        f"Run with --update-snapshots to regenerate."
    )


@pytest.fixture
def update_snapshots(request):
    """Whether the user passed --update-snapshots."""
    return request.config.getoption("--update-snapshots")


# ---------------------------------------------------------------------------
# Store patching helper
# ---------------------------------------------------------------------------
def _patch_store(monkeypatch, db_dir: str):
    """Redirect comply.store (and funded.py) to use *db_dir*."""
    import comply.store as store_mod
    db_path = os.path.join(db_dir, "scans.db")
    monkeypatch.setattr(store_mod, "_DB_DIR", db_dir)
    monkeypatch.setattr(store_mod, "_DB_PATH", db_path)
    # Clear any cached thread-local connection
    if hasattr(store_mod._local, "conn"):
        try:
            store_mod._local.conn.close()
        except Exception:
            pass
        del store_mod._local.conn

    # Also patch funded.py which has its own DB path and thread-local
    try:
        import comply.funded as funded_mod
        monkeypatch.setattr(funded_mod, "_DB_DIR", db_dir)
        monkeypatch.setattr(funded_mod, "_DB_PATH", db_path)
        if hasattr(funded_mod, "_local"):
            loc = funded_mod._local
            if hasattr(loc, "funded_conn"):
                try:
                    loc.funded_conn.close()
                except Exception:
                    pass
                del loc.funded_conn
    except (ImportError, AttributeError):
        pass


# ---------------------------------------------------------------------------
# Persona client factory
# ---------------------------------------------------------------------------
def _make_client(persona: str, tmp_path, monkeypatch):
    """Seed a persona DB and return a TestClient pointing at it."""
    from comply.test_seed import PERSONA_SEEDS, PERSONAS, SeedContext, _init_db

    seed = PERSONA_SEEDS.get(persona, 1)
    db_dir = str(tmp_path)
    db_path = os.path.join(db_dir, "scans.db")

    ctx = SeedContext(seed)
    conn = _init_db(db_path)
    PERSONAS[persona](conn, ctx)
    conn.close()

    _patch_store(monkeypatch, db_dir)

    from comply.app import create_comply_app
    from fastapi.testclient import TestClient

    return TestClient(create_comply_app())


# ---------------------------------------------------------------------------
# Named persona fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def new_user_client(tmp_path, monkeypatch):
    """TestClient with an empty (new_user) persona DB."""
    return _make_client("new_user", tmp_path, monkeypatch)


@pytest.fixture
def journey_client(tmp_path, monkeypatch):
    """TestClient with the journey persona DB (1 repo, 7 scans, gates, monitor)."""
    return _make_client("journey", tmp_path, monkeypatch)


@pytest.fixture
def single_repo_client(tmp_path, monkeypatch):
    """TestClient with the single_repo persona DB."""
    return _make_client("single_repo", tmp_path, monkeypatch)


@pytest.fixture
def multi_repo_client(tmp_path, monkeypatch):
    """TestClient with the multi_repo persona DB (5 repos, programs)."""
    return _make_client("multi_repo", tmp_path, monkeypatch)


@pytest.fixture
def power_user_client(tmp_path, monkeypatch):
    """TestClient with the power_user persona DB (12 repos, heavy usage)."""
    return _make_client("power_user", tmp_path, monkeypatch)
