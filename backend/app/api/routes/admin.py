"""Admin HTTP endpoints."""
import csv
import io
import json
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.repositories.storage import encode, verify_archive
from app.api.dependencies import admin_auth
from app.api.presenters import job_view

router = APIRouter()

def archive_rows(app, reference=None, theme=None, style=None, innovation=None, date_from=None, date_to=None):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be before date_to")
    with app.state.db.connect() as db:
        rows = db.execute("SELECT * FROM jobs WHERE status='completed' ORDER BY created_at DESC").fetchall()
    results = []
    for row in rows:
        payload = json.loads(row["payload"])
        created = date.fromisoformat(row["created_at"][:10])
        if reference and reference not in row["id"]:
            continue
        if date_from and created < date_from or date_to and created > date_to:
            continue
        if any(value and payload["answers"][field] != value for field, value in [("theme", theme), ("style", style), ("innovation", innovation)]):
            continue
        results.append(row)
    return results


@router.get("/api/v1/admin/archive", dependencies=[Depends(admin_auth)])
def archive(request: Request, reference: str | None = None, theme: str | None = None, style: str | None = None,
            innovation: str | None = None, date_from: date | None = None, date_to: date | None = None,
            limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    app = request.app
    rows = archive_rows(app, reference, theme, style, innovation, date_from, date_to)
    return {"total": len(rows), "items": [job_view(row) for row in rows[offset:offset+limit]]}


@router.get("/api/v1/admin/export", dependencies=[Depends(admin_auth)])
def export(request: Request, reference: str | None = None, theme: str | None = None, style: str | None = None,
           innovation: str | None = None, date_from: date | None = None, date_to: date | None = None,
           limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    app = request.app
    settings = app.state.settings
    rows = archive_rows(app, reference, theme, style, innovation, date_from, date_to)[offset:offset+limit]
    temp_dir = Path(tempfile.mkdtemp(prefix="stadium-export-"))
    path = temp_dir / "stadium-archive.zip"
    try:
        index = []
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for row in rows:
                payload = verify_archive(settings.data_dir, row["id"])
                index.append(payload)
                for name in ["image.png", "thumbnail.jpg", "manifest.json"]:
                    z.write(settings.data_dir / "archive" / row["id"] / name, f"{row['id']}/{name}")
            z.writestr("index.json", encode(index))
            table = io.StringIO()
            writer = csv.writer(table)
            writer.writerow(["reference", "created_at", "station", "language", "theme", "style", "innovation", "provider", "model"])
            for p in index:
                writer.writerow([p["archive_reference"], p["created_at"], p["station"], p["language"],
                                 p["answers"]["theme"], p["answers"]["style"], p["answers"]["innovation"], p["provider"], p["model"]])
            z.writestr("index.csv", table.getvalue())
    except Exception as exc:
        shutil.rmtree(temp_dir)
        raise HTTPException(503, "Archive export verification failed; check archive integrity and disk space") from exc
    return FileResponse(path, media_type="application/zip", filename="stadium-archive.zip",
                        background=BackgroundTask(shutil.rmtree, temp_dir))
