"""Generations HTTP endpoints."""
import hashlib
import json
import secrets
import shutil
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app import __version__
from app.domain.catalog import VERSION
from app.domain.design import InputError, build_design, compatibility, validate_answers
from app.providers import configured
from app.repositories.storage import encode, now, sha
from app.api.dependencies import kiosk_auth
from app.api.presenters import session_row, job_view
from app.api.schemas import GenerateRequest

router = APIRouter()


@router.post("/api/v1/sessions/{session_id}/generations", status_code=202, dependencies=[Depends(kiosk_auth)])
def generate(request: Request, session_id: UUID, body: GenerateRequest):
    app = request.app
    settings = app.state.settings
    fingerprint = hashlib.sha256(encode({"revision": body.revision, "accepted_notes": sorted(set(body.accepted_notes))}).encode()).hexdigest()
    with app.state.db.connect(immediate=True) as db:
        row = session_row(db, session_id)
        existing = db.execute("SELECT * FROM jobs WHERE session_id=? AND request_id=?", (str(session_id), str(body.request_id))).fetchone()
        if existing:
            if existing["fingerprint"] != fingerprint:
                raise HTTPException(409, "request_id already used with a different request")
            return job_view(existing)
        if not configured(settings):
            raise HTTPException(503, "Configure the selected image provider in the server environment")
        if row["revision"] != body.revision:
            raise HTTPException(409, "Session changed; review the latest choices")
        try:
            answers = validate_answers(json.loads(row["answers"]), complete=True, allow_free_text=settings.allow_free_text)
        except InputError as exc:
            raise HTTPException(422, str(exc)) from exc
        notes = compatibility(answers)
        if {n["code"] for n in notes} != set(body.accepted_notes):
            raise HTTPException(409, {"message": "Confirm the current compatibility notes before generation", "notes": notes})
        if db.execute("SELECT 1 FROM jobs WHERE session_id=? AND status IN ('queued','generating','saving')", (str(session_id),)).fetchone():
            raise HTTPException(409, "This session already has an active generation")
        pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','generating','saving')").fetchone()[0]
        if pending >= settings.max_pending_jobs:
            raise HTTPException(429, "Generation queue is full; try again later")
        if shutil.disk_usage(settings.data_dir).free < settings.min_free_disk_mb * 1024**2:
            raise HTTPException(507, "Insufficient local archive storage")
        job_id, timestamp = str(uuid4()), now()
        payload = {"archive_reference": job_id, "session_id": str(session_id), "created_at": timestamp,
                   "station": row["station"], "language": row["language"], "answers": answers,
                   "revision": body.revision, "accepted_notes": notes, "questionnaire_version": VERSION,
                   "software_version": __version__, "asset_version": "schematic-v1" if settings.provider == "mock" else None,
                   "provider": settings.provider, "model": app.state.provider.model,
                   "design": build_design(answers, secrets.randbits(32)), "attempts": []}
        db.execute("INSERT INTO jobs(id,session_id,request_id,fingerprint,status,created_at,updated_at,payload) VALUES (?,?,?,?,?,?,?,?)",
                   (job_id, str(session_id), str(body.request_id), fingerprint, "queued", timestamp, timestamp, encode(payload)))
        return job_view(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


@router.get("/api/v1/generations/{job_id}", dependencies=[Depends(kiosk_auth)])
def get_generation(request: Request, job_id: UUID):
    app = request.app
    row = app.state.db.job(str(job_id))
    if not row:
        raise HTTPException(404, "Generation not found")
    return job_view(row)


@router.get("/api/v1/generations/{job_id}/{asset}", dependencies=[Depends(kiosk_auth)])
def get_asset(request: Request, job_id: UUID, asset: Literal["image", "thumbnail"]):
    app = request.app
    settings = app.state.settings
    row = app.state.db.job(str(job_id))
    if not row:
        raise HTTPException(404, "Generation not found")
    if row["status"] != "completed":
        raise HTTPException(409, "Verified archive is not ready")
    name = "image.png" if asset == "image" else "thumbnail.jpg"
    path = settings.data_dir / "archive" / str(job_id) / name
    metadata = json.loads(row["payload"])["image"]
    expected = metadata["sha256" if asset == "image" else "thumbnail_sha256"]
    try:
        if sha(path.read_bytes()) != expected:
            raise ValueError("checksum")
    except (OSError, ValueError):
        raise HTTPException(503, "Archive file is missing or damaged; restore from backup")
    return FileResponse(path, media_type="image/png" if asset == "image" else "image/jpeg")
