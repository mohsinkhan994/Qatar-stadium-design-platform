import asyncio
import csv
import fcntl
import hashlib
import hmac
import io
import json
import secrets
import shutil
import tempfile
import zipfile
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from . import __version__
from .catalog import QUESTIONS, VERSION
from .config import Settings
from .design import InputError, build_design, compatibility, validate_answers
from .providers import configured, provider_for
from .storage import Database, encode, now, recover, sha, verify_archive
from .worker import Worker


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(StrictModel):
    language: Literal["en"] = "en"


class AnswerPatch(StrictModel):
    revision: int = Field(ge=0, strict=True)
    answers: dict[str, Any]


class GenerateRequest(StrictModel):
    request_id: UUID
    revision: int = Field(ge=0, strict=True)
    accepted_notes: list[str] = Field(default_factory=list, max_length=10)


def create_app(settings=None, provider=None):
    settings = settings or Settings.from_env()
    settings.validate()

    @asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        # One local worker owns each database. Prevent duplicate billing from multiple processes.
        lock = (settings.data_dir / "worker.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError("This data directory already has a running backend. Use exactly one uvicorn worker.")
        try:
            app.state.db = Database(settings.data_dir)
            app.state.provider = provider or provider_for(settings)
            recover(app.state.db)
            worker = Worker(app.state.db, settings, app.state.provider)
            task = asyncio.create_task(worker.run())
            try:
                yield
            finally:
                worker.stopping.set()
                await task
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    app = FastAPI(title="Stadium Design API", version=__version__, lifespan=lifespan,
                  description="Mock output is a labelled fixture. Local image generation uses CPU, CUDA or Apple MPS, depending on configuration.")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "backend", "testserver"])
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type", "X-Admin-Key"])

    def kiosk_auth(authorization: str | None = Header(default=None)):
        if settings.kiosk_api_key and not hmac.compare_digest(authorization or "", f"Bearer {settings.kiosk_api_key}"):
            raise HTTPException(401, "Invalid kiosk token")

    def admin_auth(x_admin_key: str | None = Header(default=None)):
        if not settings.admin_api_key:
            raise HTTPException(503, "Set ADMIN_API_KEY on the backend to enable staff access")
        if not hmac.compare_digest(x_admin_key or "", settings.admin_api_key):
            raise HTTPException(401, "Invalid staff token")

    def session_row(db, session_id):
        row = db.execute("SELECT * FROM sessions WHERE id=?", (str(session_id),)).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        return row

    def session_view(row):
        data = dict(row)
        data["answers"] = json.loads(data["answers"])
        data["answered_count"] = len(data["answers"])
        return data

    def job_view(row):
        payload = json.loads(row["payload"])
        completed = row["status"] == "completed"
        result = {"id": row["id"], "session_id": row["session_id"], "status": row["status"],
                  "created_at": row["created_at"], "updated_at": row["updated_at"],
                  "provider": payload["provider"], "is_mock": payload["provider"] == "mock",
                  "can_finish": completed,
                  "error": {"code": row["error_code"], "message": row["error_message"]} if row["error_code"] else None}
        if completed:
            result["result"] = {
                "archive_reference": row["id"], "answers": payload["answers"],
                "design": {k: v for k, v in payload["design"].items()
                           if k not in {"prompt", "local_prompt"}},
                "image": payload["image"], "image_url": f"/api/v1/generations/{row['id']}/image",
                "thumbnail_url": f"/api/v1/generations/{row['id']}/thumbnail",
            }
        return result

    @app.get("/health")
    def health():
        free = shutil.disk_usage(settings.data_dir).free
        with app.state.db.connect() as db:
            pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','generating','saving')").fetchone()[0]
        return {"status": "ok" if free >= settings.min_free_disk_mb * 1024**2 else "low_storage",
                "version": __version__, "provider": settings.provider, "model": app.state.provider.model,
                "provider_configured": configured(settings),
                "pending_jobs": pending, "free_disk_mb": free // 1024**2,
                "capabilities": {"languages": ["en"], "arabic_copy": "pending museum approval",
                                 "free_text_signature": settings.allow_free_text,
                                 "offline_ai": settings.provider == "local" and configured(settings),
                                 "mock_mode": settings.provider == "mock"}}

    @app.get("/api/v1/questionnaire", dependencies=[Depends(kiosk_auth)])
    def questionnaire():
        return {"version": VERSION, "language": "en", "questions": QUESTIONS,
                "free_text_enabled": settings.allow_free_text,
                "note": "Multiple-choice questions currently require at least one selection; confirm this interpretation with the museum."}

    @app.post("/api/v1/sessions", status_code=201, dependencies=[Depends(kiosk_auth)])
    def create_session(body: SessionCreate):
        session_id, timestamp = str(uuid4()), now()
        with app.state.db.connect() as db:
            db.execute("INSERT INTO sessions(id,language,station,created_at,updated_at) VALUES (?,?,?,?,?)",
                       (session_id, body.language, settings.station_id, timestamp, timestamp))
            return session_view(session_row(db, session_id))

    @app.get("/api/v1/sessions/{session_id}", dependencies=[Depends(kiosk_auth)])
    def get_session(session_id: UUID):
        with app.state.db.connect() as db:
            result = session_view(session_row(db, session_id))
            rows = db.execute("SELECT * FROM jobs WHERE session_id=? ORDER BY created_at DESC", (str(session_id),)).fetchall()
        result["generations"] = [job_view(row) for row in rows]
        return result

    @app.patch("/api/v1/sessions/{session_id}/answers", dependencies=[Depends(kiosk_auth)])
    def patch_answers(session_id: UUID, body: AnswerPatch):
        with app.state.db.connect(immediate=True) as db:
            row = session_row(db, session_id)
            if row["revision"] != body.revision:
                raise HTTPException(409, "Session changed; fetch the current revision before editing")
            if db.execute("SELECT 1 FROM jobs WHERE session_id=? AND status IN ('queued','generating','saving')", (str(session_id),)).fetchone():
                raise HTTPException(409, "Wait for the active generation before editing choices")
            answers = json.loads(row["answers"])
            for key, value in body.answers.items():
                if value is None:
                    from .catalog import BY_ID
                    if key not in BY_ID:
                        raise HTTPException(422, f"Unknown question: {key}")
                    answers.pop(key, None)
                else:
                    answers[key] = value
            try:
                answers = validate_answers(answers, allow_free_text=settings.allow_free_text)
            except InputError as exc:
                raise HTTPException(422, str(exc)) from exc
            db.execute("UPDATE sessions SET answers=?,revision=revision+1,updated_at=? WHERE id=?",
                       (encode(answers), now(), str(session_id)))
            return session_view(session_row(db, session_id))

    @app.get("/api/v1/sessions/{session_id}/review", dependencies=[Depends(kiosk_auth)])
    def review(session_id: UUID):
        with app.state.db.connect() as db:
            row = session_row(db, session_id)
        try:
            answers = validate_answers(json.loads(row["answers"]), complete=True, allow_free_text=settings.allow_free_text)
        except InputError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"session_id": str(session_id), "revision": row["revision"], "answers": answers,
                "notes_to_confirm": compatibility(answers), "provider": settings.provider,
                "is_mock": settings.provider == "mock", "provider_configured": configured(settings)}

    @app.post("/api/v1/sessions/{session_id}/generations", status_code=202, dependencies=[Depends(kiosk_auth)])
    def generate(session_id: UUID, body: GenerateRequest):
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

    @app.get("/api/v1/generations/{job_id}", dependencies=[Depends(kiosk_auth)])
    def get_generation(job_id: UUID):
        row = app.state.db.job(str(job_id))
        if not row:
            raise HTTPException(404, "Generation not found")
        return job_view(row)

    @app.get("/api/v1/generations/{job_id}/{asset}", dependencies=[Depends(kiosk_auth)])
    def get_asset(job_id: UUID, asset: Literal["image", "thumbnail"]):
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

    @app.post("/api/v1/sessions/{session_id}/finish", dependencies=[Depends(kiosk_auth)])
    def finish(session_id: UUID):
        with app.state.db.connect() as db:
            session_row(db, session_id)
            rows = db.execute("SELECT * FROM jobs WHERE session_id=? ORDER BY created_at DESC", (str(session_id),)).fetchall()
        if not rows or rows[0]["status"] != "completed":
            raise HTTPException(409, "The latest generation must be saved before finishing")
        try:
            verify_archive(settings.data_dir, rows[0]["id"])
        except (OSError, ValueError, KeyError):
            raise HTTPException(503, "Archive verification failed; do not clear the session")
        return {"can_reset": True, "archive_reference": rows[0]["id"], "message": "Start a new anonymous session. The archived design is retained."}

    def archive_rows(reference=None, theme=None, style=None, innovation=None, date_from=None, date_to=None):
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

    @app.get("/api/v1/admin/archive", dependencies=[Depends(admin_auth)])
    def archive(reference: str | None = None, theme: str | None = None, style: str | None = None,
                innovation: str | None = None, date_from: date | None = None, date_to: date | None = None,
                limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
        rows = archive_rows(reference, theme, style, innovation, date_from, date_to)
        return {"total": len(rows), "items": [job_view(row) for row in rows[offset:offset+limit]]}

    @app.get("/api/v1/admin/export", dependencies=[Depends(admin_auth)])
    def export(reference: str | None = None, theme: str | None = None, style: str | None = None,
               innovation: str | None = None, date_from: date | None = None, date_to: date | None = None,
               limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
        rows = archive_rows(reference, theme, style, innovation, date_from, date_to)[offset:offset+limit]
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

    frontend = Path(__file__).resolve().parent.parent / "frontend"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
