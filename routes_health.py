"""Liveness endpoint.

This lives in its own module on purpose. `GET /health` previously sat at the
bottom of `routes_billing.py`, under a comment separating it from the license
handlers, and it was deleted along with that module during the standalone
carve-out. Nothing noticed for five months, because the only things that call it
are a Dockerfile HEALTHCHECK, two tests, and a dashboard badge -- none of which
anyone reads when they are already red.

Health is not a billing concern and must not be filed under one again.

Recovered verbatim from `git show v1.3.2:routes_billing.py`. The response shape
is load-bearing and is not free to simplify:
  status  -- tests/test_health_config.py:12
  db      -- tests/test_health_config.py:13
  version -- dashboard/app.js:1056 renders it as the version badge
A minimal {"status": "ok"} turns both tests green and freezes the badge on a
stale version forever, which is a passing gate over a live defect.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    from comply import __version__
    from comply.store import _get_conn
    db_ok = True
    try:
        _get_conn().execute("SELECT 1").fetchone()
    except Exception:
        db_ok = False
    return {"status": "ok", "service": "comply", "version": __version__, "db": db_ok}
