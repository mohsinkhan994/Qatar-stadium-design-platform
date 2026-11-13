"""Health HTTP endpoints."""
import shutil

from fastapi import APIRouter, Request

from app import __version__
from app.providers import configured

router = APIRouter()


@router.get("/health")
def health(request: Request):
    app = request.app
    settings = app.state.settings
    free = shutil.disk_usage(settings.data_dir).free
    with app.state.db.connect() as db:
        pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','generating','validating','retrying','saving')").fetchone()[0]
    return {"status": "ok" if free >= settings.min_free_disk_mb * 1024**2 else "low_storage",
            "version": __version__, "provider": settings.provider, "model": app.state.provider.model,
            "provider_configured": configured(settings),
            "pending_jobs": pending, "free_disk_mb": free // 1024**2,
            "capabilities": {"languages": ["en"], "arabic_copy": "pending museum approval",
                             "free_text_signature": settings.allow_free_text,
                             "offline_ai": settings.provider == "local" and configured(settings),
                             "mock_mode": settings.provider == "mock"}}
