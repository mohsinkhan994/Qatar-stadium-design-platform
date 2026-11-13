from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.providers.mock import MockProvider
from app.repositories.storage import Database, recover
from test_backend import ANSWERS, completed


def test_queued_cancellation_is_idempotent_and_releases_session(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, min_free_disk_mb=0))
    app.state.db = Database(tmp_path)
    app.state.provider = MockProvider()
    # Deliberately do not enter the lifespan: no worker races this queued job.
    client = TestClient(app)
    session = client.post("/api/v1/sessions", json={}).json()
    sid = session["id"]
    patched = client.patch(
        f"/api/v1/sessions/{sid}/answers", json={"revision": 0, "answers": ANSWERS}
    ).json()
    review = client.get(f"/api/v1/sessions/{sid}/review").json()
    response = client.post(
        f"/api/v1/sessions/{sid}/generations",
        json={
            "request_id": str(uuid4()),
            "revision": patched["revision"],
            "accepted_notes": [n["code"] for n in review["notes_to_confirm"]],
        },
    )
    assert response.status_code == 202
    jid = response.json()["id"]
    for _ in range(2):
        response = client.post(f"/api/v1/generations/{jid}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
    assert app.state.db.claim() is None
    assert (
        client.patch(
            f"/api/v1/sessions/{sid}/answers",
            json={"revision": patched["revision"], "answers": {"roof": "open"}},
        ).status_code
        == 200
    )


def test_active_cancellation_is_explicitly_rejected(tmp_path):
    with TestClient(
        create_app(Settings(data_dir=tmp_path, min_free_disk_mb=0))
    ) as client:
        _, result = completed(client)
        assert (
            client.post(f"/api/v1/generations/{result['id']}/cancel").status_code == 409
        )


def test_recovery_preserves_archive_after_late_database_failure(tmp_path):
    with TestClient(
        create_app(Settings(data_dir=tmp_path, min_free_disk_mb=0))
    ) as client:
        _, result = completed(client)
        db = client.app.state.db
        db.update_job(result["id"], "failed", error_code="processing_failed")
        recover(db)
        assert db.job(result["id"])["status"] == "completed"
