"""Sessions HTTP endpoints."""
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from app.domain.catalog import BY_ID
from app.domain.design import InputError, compatibility, validate_answers
from app.providers import configured
from app.repositories.storage import encode, now, verify_archive
from app.api.dependencies import kiosk_auth
from app.api.presenters import session_row, session_view, job_view
from app.api.schemas import SessionCreate, AnswerPatch

router = APIRouter()


@router.post("/api/v1/sessions", status_code=201, dependencies=[Depends(kiosk_auth)])
def create_session(request: Request, body: SessionCreate):
    app = request.app
    settings = app.state.settings
    session_id, timestamp = str(uuid4()), now()
    with app.state.db.connect() as db:
        db.execute("INSERT INTO sessions(id,language,station,created_at,updated_at) VALUES (?,?,?,?,?)",
                   (session_id, body.language, settings.station_id, timestamp, timestamp))
        return session_view(session_row(db, session_id))


@router.get("/api/v1/sessions/{session_id}", dependencies=[Depends(kiosk_auth)])
def get_session(request: Request, session_id: UUID):
    app = request.app
    with app.state.db.connect() as db:
        result = session_view(session_row(db, session_id))
        rows = db.execute("SELECT * FROM jobs WHERE session_id=? ORDER BY created_at DESC", (str(session_id),)).fetchall()
    result["generations"] = [job_view(row) for row in rows]
    return result


@router.patch("/api/v1/sessions/{session_id}/answers", dependencies=[Depends(kiosk_auth)])
def patch_answers(request: Request, session_id: UUID, body: AnswerPatch):
    app = request.app
    settings = app.state.settings
    with app.state.db.connect(immediate=True) as db:
        row = session_row(db, session_id)
        if row["revision"] != body.revision:
            raise HTTPException(409, "Session changed; fetch the current revision before editing")
        if db.execute("SELECT 1 FROM jobs WHERE session_id=? AND status IN ('queued','generating','validating','retrying','saving')", (str(session_id),)).fetchone():
            raise HTTPException(409, "Wait for the active generation before editing choices")
        answers = json.loads(row["answers"])
        for key, value in body.answers.items():
            if value is None:
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


@router.get("/api/v1/sessions/{session_id}/review", dependencies=[Depends(kiosk_auth)])
def review(request: Request, session_id: UUID):
    app = request.app
    settings = app.state.settings
    with app.state.db.connect() as db:
        row = session_row(db, session_id)
    try:
        answers = validate_answers(json.loads(row["answers"]), complete=True, allow_free_text=settings.allow_free_text)
    except InputError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"session_id": str(session_id), "revision": row["revision"], "answers": answers,
            "notes_to_confirm": compatibility(answers), "provider": settings.provider,
            "is_mock": settings.provider == "mock", "provider_configured": configured(settings)}


@router.post("/api/v1/sessions/{session_id}/finish", dependencies=[Depends(kiosk_auth)])
def finish(request: Request, session_id: UUID):
    app = request.app
    settings = app.state.settings
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
