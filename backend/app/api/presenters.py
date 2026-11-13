"""Database row lookup and public response formatting."""
import json
from fastapi import HTTPException


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
                       if k not in {"prompt", "local_prompt", "flux_prompt", "sections", "constraints", "reference"}},
            "image": payload["image"], "image_url": f"/api/v1/generations/{row['id']}/image",
            "thumbnail_url": f"/api/v1/generations/{row['id']}/thumbnail",
        }
    return result
