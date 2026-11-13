import io
import json
from PIL import Image
from app.core.config import Settings
from app.domain.design import build_design
from app.providers.base import Generation
from app.services.validation import WEIGHTS
from app.services.worker import Worker

from test_backend import ANSWERS


class Database:
    def __init__(self):
        self.updates = []

    def update_job(self, *args):
        self.updates.append(args)

    def image_exists(self, *args):
        return False

    def similar_image_exists(self, *args):
        return False


class Provider:
    name = "local"
    model = "black-forest-labs/flux-3-image-klein"

    def __init__(self):
        self.designs = []

    def generate(self, design):
        self.designs.append(design.copy())
        data = io.BytesIO()
        Image.new("RGB", (128, 128), "green").save(data, "PNG")
        return Generation(data.getvalue(), {"backend": "test"})


class Evaluator:
    def __init__(self, always_fail=False):
        self.calls = 0
        self.always_fail = always_fail

    def evaluate(self, image, design):
        assert image.startswith(b"\x89PNG")
        self.calls += 1
        return {
            "criteria": dict.fromkeys(WEIGHTS, 90),
            "critical_constraints_passed": self.calls > 1 and not self.always_fail,
            "missing_features": ["Continuous oval running track"],
        }


def run(tmp_path, evaluator):
    db = Database()
    provider = Provider()
    settings = Settings(provider="local", data_dir=tmp_path, min_free_disk_mb=0)
    answers = {**ANSWERS, "use": "athletics"}
    payload = {
        "archive_reference": "test-job",
        "provider": provider.name,
        "model": provider.model,
        "answers": answers,
        "design": build_design(answers, 42),
        "attempts": [],
    }
    Worker(db, settings, provider, evaluator).process(
        {"id": "test-job", "payload": json.dumps(payload)}
    )
    return db, provider


def test_critical_retry_preserves_signature_and_archives(tmp_path):
    db, provider = run(tmp_path, Evaluator())
    assert db.updates[-1][1] == "completed"
    assert len(provider.designs) == 2
    a, b = provider.designs
    assert a["signature"] == b["signature"]
    assert a["variation"]["seed"] != b["variation"]["seed"]
    assert "Correct these observed omissions" in b["flux_prompt"]
    assert {"generating", "validating", "retrying", "saving", "completed"} <= {
        u[1] for u in db.updates
    }
    manifest = json.loads((tmp_path / "archive/test-job/manifest.json").read_text())
    assert manifest["validation"]["status"] == "passed"
    assert len(manifest["attempts"]) == 2
    assert manifest["attempts"][0]["duration_seconds"] >= 0


def test_retry_limit_and_retained_failed_candidates(tmp_path):
    db, provider = run(tmp_path, Evaluator(True))
    assert len(provider.designs) == 2
    assert db.updates[-1][1] == "failed"
    assert db.updates[-1][3] == "visual_validation_failed"
    assert (tmp_path / "candidates/test-job/1.png").exists()
    assert (tmp_path / "candidates/test-job/2.png").exists()


def test_no_evaluator_does_not_claim_accuracy(tmp_path):
    db, provider = run(tmp_path, None)
    assert len(provider.designs) == 1
    manifest = json.loads((tmp_path / "archive/test-job/manifest.json").read_text())
    assert manifest["validation"]["status"] == "unavailable"
    assert manifest["validation"]["overall_score"] is None


def test_evaluator_failure_retains_candidate_without_retry(tmp_path):
    class Broken:
        def evaluate(self, *args):
            raise RuntimeError("Evaluator offline")

    db, provider = run(tmp_path, Broken())
    assert len(provider.designs) == 1
    assert db.updates[-1][1] == "failed"
    assert db.updates[-1][3] == "processing_failed"
    assert (tmp_path / "candidates/test-job/1.png").exists()


def test_low_score_without_critical_failure_does_not_regenerate(tmp_path):
    class LowScore:
        def evaluate(self, *args):
            return {
                "criteria": dict.fromkeys(WEIGHTS, 80),
                "critical_constraints_passed": True,
            }

    db, provider = run(tmp_path, LowScore())
    assert len(provider.designs) == 1
    assert db.updates[-1][1] == "failed"
