"""REST endpoints for the Comply web server (facade assembling sub-routers)."""
from fastapi import APIRouter

from comply.routes_scan import router as scan_router
from comply.routes_posture import router as posture_router
from comply.routes_forecast import router as forecast_router
from comply.routes_import import router as import_router

router = APIRouter()
router.include_router(scan_router)
router.include_router(posture_router)
router.include_router(forecast_router)
router.include_router(import_router)
