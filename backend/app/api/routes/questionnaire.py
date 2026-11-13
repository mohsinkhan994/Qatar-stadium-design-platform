"""Questionnaire HTTP endpoints."""

from fastapi import APIRouter, Depends, Request

from app.domain.catalog import QUESTIONS, VERSION
from app.api.dependencies import kiosk_auth

router = APIRouter()


@router.get("/api/v1/questionnaire", dependencies=[Depends(kiosk_auth)])
def questionnaire(request: Request):
    app = request.app
    settings = app.state.settings
    return {"version": VERSION, "language": "en", "questions": QUESTIONS,
            "free_text_enabled": settings.allow_free_text,
            "note": "Multiple-choice questions currently require at least one selection; confirm this interpretation with the museum."}
