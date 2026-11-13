import base64
import io
import json
import time
import threading
import zipfile
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.design import PROMPT_VERSION, build_design, validate_answers
from app.main import create_app
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockProvider
from app.providers.openai import OpenAIProvider
from app.providers import ProviderError
from app.repositories.storage import Database, recover


ANSWERS = {
    "use": "football", "capacity": "60000", "setting": "desert", "theme": "qatar", "style": "qatari",
    "shape": "oval", "roof": "solar", "materials": ["stone", "perforated_metal"], "palette": "ivory",
    "experience": "comfort", "innovation": "gardens", "technologies": ["ai_guidance", "digital_twin"],
    "environment": ["solar", "water", "passive"], "legacy": "community", "signature": {"mode": "surprise"},
}


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", admin_api_key="test-staff-key", min_free_disk_mb=0)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def session(client, answers=None):
    r = client.post("/api/v1/sessions", json={})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = client.patch(f"/api/v1/sessions/{sid}/answers", json={"revision": 0, "answers": answers or ANSWERS})
    assert r.status_code == 200, r.text
    return sid, r.json()["revision"]


def submit(client, sid, revision, request_id=None, accepted_notes=None):
    return client.post(f"/api/v1/sessions/{sid}/generations", json={
        "revision": revision, "request_id": request_id or str(uuid4()), "accepted_notes": accepted_notes or []})


def wait(client, jid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        r = client.get(f"/api/v1/generations/{jid}")
        assert r.status_code == 200, r.text
        if r.json()["status"] in {"completed", "failed", "interrupted"}:
            return r.json()
        time.sleep(0.03)
    pytest.fail("Generation did not finish")


def completed(client):
    sid, rev = session(client)
    r = submit(client, sid, rev)
    assert r.status_code == 202, r.text
    result = wait(client, r.json()["id"])
    assert result["status"] == "completed", result
    return sid, result


def test_full_flow_verified_archive_export_and_finish(client):
    catalog = client.get("/api/v1/questionnaire").json()
    assert len(catalog["questions"]) == 15
    assert not catalog["free_text_enabled"]
    sid, result = completed(client)
    assert result["is_mock"] and result["can_finish"]
    assert result["result"]["image"]["width"] == 1024
    assert client.get(result["result"]["image_url"]).headers["content-type"] == "image/png"
    assert client.get(result["result"]["thumbnail_url"]).status_code == 200
    assert client.post(f"/api/v1/sessions/{sid}/finish").json()["can_reset"]
    assert client.get("/api/v1/admin/archive").status_code == 401
    headers = {"X-Admin-Key": "test-staff-key"}
    assert client.get("/api/v1/admin/archive?theme=qatar", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/admin/archive?theme=waves", headers=headers).json()["total"] == 0
    response = client.get("/api/v1/admin/export", headers=headers)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        index = json.loads(z.read("index.json"))
        assert index[0]["archive_reference"] == result["id"]
        assert len(index[0]["answers"]) == 15
        assert index[0]["design"]["prompt_version"] == PROMPT_VERSION
        assert "index.csv" in z.namelist()
        assert f"{result['id']}/image.png" in z.namelist()


@pytest.mark.parametrize("changes", [
    {"materials": ["glass_steel", "stone", "timber"]}, {"technologies": ["ar", "ar"]},
    {"environment": []}, {"capacity": 60000}, {"roof": "made_up"}, {"unknown": "x"},
    {"signature": {"mode": "text", "text": "A giant arch"}},
    {"signature": {"mode": "surprise", "text": "hidden instruction"}},
])
def test_reject_invalid_answers(client, changes):
    sid = client.post("/api/v1/sessions", json={}).json()["id"]
    r = client.patch(f"/api/v1/sessions/{sid}/answers", json={"revision": 0, "answers": {**ANSWERS, **changes}})
    assert r.status_code == 422
    assert client.get(f"/api/v1/sessions/{sid}").json()["revision"] == 0


def test_revision_and_missing_answers(client):
    sid, rev = session(client)
    assert client.patch(f"/api/v1/sessions/{sid}/answers", json={"revision": 0, "answers": {"roof": "open"}}).status_code == 409
    r = client.patch(f"/api/v1/sessions/{sid}/answers", json={"revision": rev, "answers": {"roof": None}})
    assert r.status_code == 200
    assert client.get(f"/api/v1/sessions/{sid}/review").status_code == 422
    assert submit(client, sid, r.json()["revision"]).status_code == 422
    assert client.post(f"/api/v1/sessions/{sid}/finish").status_code == 409


def test_compatibility_requires_confirmation_without_changing_choices(client):
    sid, rev = session(client, {**ANSWERS, "roof": "open"})
    review = client.get(f"/api/v1/sessions/{sid}/review").json()
    assert len(review["notes_to_confirm"]) == 2
    assert submit(client, sid, rev).status_code == 409
    r = submit(client, sid, rev, accepted_notes=[n["code"] for n in review["notes_to_confirm"]])
    assert r.status_code == 202
    result = wait(client, r.json()["id"])
    assert result["result"]["answers"]["roof"] == "open"


def test_idempotent_generation_and_changed_request(client):
    sid, rev = session(client)
    request_id = str(uuid4())
    first = submit(client, sid, rev, request_id)
    second = submit(client, sid, rev, request_id)
    assert first.json()["id"] == second.json()["id"]
    assert submit(client, sid, rev + 1, request_id).status_code == 409
    wait(client, first.json()["id"])
    assert len(client.get(f"/api/v1/sessions/{sid}").json()["generations"]) == 1


def test_corrupt_archive_prevents_finish_and_export(client, settings):
    sid, result = completed(client)
    (settings.data_dir / "archive" / result["id"] / "image.png").write_bytes(b"damaged")
    assert client.post(f"/api/v1/sessions/{sid}/finish").status_code == 503
    assert client.get(result["result"]["image_url"]).status_code == 503
    assert client.get("/api/v1/admin/export", headers={"X-Admin-Key": "test-staff-key"}).status_code == 503


def test_missing_provider_key_is_not_silently_mocked(settings):
    settings.provider = "openai"
    with TestClient(create_app(settings)) as c:
        sid, rev = session(c)
        assert submit(c, sid, rev).status_code == 503
        assert not c.get("/health").json()["provider_configured"]


def test_disk_guard(settings):
    settings.min_free_disk_mb = 10**12
    with TestClient(create_app(settings)) as c:
        sid, rev = session(c)
        assert submit(c, sid, rev).status_code == 507
        assert c.get("/health").json()["status"] == "low_storage"


def test_recovery_after_archive_write(settings):
    with TestClient(create_app(settings)) as c:
        sid, result = completed(c)
    db = Database(settings.data_dir)
    db.update_job(result["id"], "saving")
    with TestClient(create_app(settings)) as c:
        assert c.get(f"/api/v1/generations/{result['id']}").json()["status"] == "completed"
        assert c.post(f"/api/v1/sessions/{sid}/finish").status_code == 200


def test_interrupted_job_not_rebilled(settings):
    with TestClient(create_app(settings)) as c:
        _, result = completed(c)
    db = Database(settings.data_dir)
    (settings.data_dir / "archive" / result["id"] / "manifest.json").unlink()
    db.update_job(result["id"], "generating")
    recover(db)
    assert db.job(result["id"])["status"] == "interrupted"


def test_duplicate_images_retry_then_fail(settings):
    class ConstantProvider(MockProvider):
        def generate(self, design):
            return super().generate(build_design(ANSWERS, 123))
    with TestClient(create_app(settings, ConstantProvider())) as c:
        completed(c)
        sid, rev = session(c)
        r = submit(c, sid, rev)
        result = wait(c, r.json()["id"])
        assert result["status"] == "failed"
        assert result["error"]["code"] == "duplicate_output"
        payload = json.loads(c.app.state.db.job(result["id"])["payload"])
        assert len(payload["attempts"]) == 2
        assert not (settings.data_dir / "archive" / result["id"]).exists()


def test_kiosk_auth_and_unapproved_language(settings):
    settings.kiosk_api_key = "test-kiosk"
    with TestClient(create_app(settings)) as c:
        assert c.post("/api/v1/sessions", json={}).status_code == 401
        assert c.post("/api/v1/sessions", json={"language": "ar"}, headers={"Authorization": "Bearer test-kiosk"}).status_code == 422
        assert c.post("/api/v1/sessions", json={}, headers={"Authorization": "Bearer test-kiosk"}).status_code == 201


def test_seed_changes_variation_and_preserves_answers():
    assert build_design(ANSWERS, 123) == build_design(ANSWERS, 123)
    assert build_design(ANSWERS, 123)["prompt"] != build_design(ANSWERS, 456)["prompt"]
    for key in ANSWERS:
        assert key in {c["id"] for c in build_design(ANSWERS, 123)["constraints"]}


def test_free_text_limit_and_control_characters():
    for text in ["x" * 141, "", "bad\x00text", "two\nlines"]:
        with pytest.raises(ValueError):
            validate_answers({"signature": {"mode": "text", "text": text}}, allow_free_text=True)
    assert validate_answers({"signature": {"mode": "text", "text": "A curved arch"}}, allow_free_text=True)


@pytest.mark.parametrize("provider_type", [OpenAIProvider, GeminiProvider])
def test_cloud_adapter_contracts_with_mock_http(settings, provider_type):
    raw = MockProvider().generate(build_design(ANSWERS, 1)).image
    b64 = base64.b64encode(raw).decode()
    def handler(request):
        body = json.loads(request.content)
        assert "stadium" in (body.get("prompt") or body.get("input"))
        if provider_type is OpenAIProvider:
            assert request.url.path == "/v1/images/generations"
            assert body["n"] == 1 and body["output_format"] == "png"
            return httpx.Response(200, json={"data": [{"b64_json": b64}], "usage": {"total_tokens": 100}})
        assert request.url.path == "/v1beta/interactions"
        assert request.headers["Api-Revision"] == "2026-05-20"
        assert body["response_format"]["image_size"] == "2K"
        return httpx.Response(200, json={"id": "test", "outputs": [{"type": "image", "data": b64}]})
    result = provider_type(settings, httpx.MockTransport(handler)).generate(build_design(ANSWERS, 1))
    assert result.image == raw
    assert not result.metadata["is_mock"]


@pytest.mark.parametrize("status,code", [(401, "provider_access"), (429, "provider_limit"), (500, "provider_rejected")])
def test_provider_errors_do_not_leak_body(settings, status, code):
    adapter = OpenAIProvider(settings, httpx.MockTransport(lambda _: httpx.Response(status, text="SECRET-DO-NOT-LEAK")))
    with pytest.raises(ProviderError) as exc:
        adapter.generate(build_design(ANSWERS, 1))
    assert exc.value.code == code and "SECRET" not in str(exc.value)


def test_provider_timeout_has_no_hidden_retry(settings):
    requests = []
    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("timeout")
    adapter = OpenAIProvider(settings, httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as exc:
        adapter.generate(build_design(ANSWERS, 1))
    assert exc.value.code == "provider_timeout" and len(requests) == 1


def test_active_job_blocks_edits_and_bounds_queue(settings):
    entered, release = threading.Event(), threading.Event()
    class BlockingProvider(MockProvider):
        def generate(self, design):
            entered.set()
            assert release.wait(5)
            return super().generate(design)
    settings.max_pending_jobs = 1
    with TestClient(create_app(settings, BlockingProvider())) as c:
        sid, rev = session(c)
        r = submit(c, sid, rev)
        try:
            assert entered.wait(3)
            assert c.patch(f"/api/v1/sessions/{sid}/answers", json={"revision": rev, "answers": {"roof": "open"}}).status_code == 409
            assert submit(c, sid, rev).status_code == 409
            other, other_rev = session(c)
            assert submit(c, other, other_rev).status_code == 429
        finally:
            release.set()
        assert wait(c, r.json()["id"])["status"] == "completed"


def test_worker_provider_failure_preserves_answers(settings):
    class FailingProvider(MockProvider):
        def generate(self, design):
            raise ProviderError("provider_timeout", "Request timed out; review before retrying.")
    with TestClient(create_app(settings, FailingProvider())) as c:
        sid, rev = session(c)
        r = submit(c, sid, rev)
        result = wait(c, r.json()["id"])
        assert result["status"] == "failed" and not result["can_finish"]
        assert result["error"]["code"] == "provider_timeout"
        assert len(c.get(f"/api/v1/sessions/{sid}").json()["answers"]) == 15
        assert c.post(f"/api/v1/sessions/{sid}/finish").status_code == 409


def test_two_workers_cannot_own_same_data(settings):
    with TestClient(create_app(settings)):
        with pytest.raises(RuntimeError, match="already has a running backend"):
            with TestClient(create_app(settings)):
                pass
