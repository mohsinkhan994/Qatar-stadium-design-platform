import io
import json
import sys
from PIL import Image
from app.providers.base import Generation
from scripts import benchmark


def test_pipeline_benchmark_uses_worker_and_keeps_visual_metrics_null(
    monkeypatch, tmp_path
):
    class Provider:
        name = "local"
        uses_mlx = True

        def __init__(self, settings):
            self.model = settings.local_model

        def generate(self, design):
            data = io.BytesIO()
            Image.new(
                "RGB", (128, 128), (design["variation"]["seed"] % 255, 30, 40)
            ).save(data, "PNG")
            return Generation(data.getvalue(), {"cold_start": False})

        def close(self):
            pass

    monkeypatch.setattr(benchmark, "Flux3Provider", Provider)
    monkeypatch.setenv("VISUAL_EVALUATOR_COMMAND", "[]")
    monkeypatch.setenv("PERCEPTUAL_DUPLICATE_DISTANCE", "-1")
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark", "--run", "--pipeline", "--limit", "2", "--output", str(tmp_path)],
    )
    benchmark.main()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["generated"] == 2
    assert summary["errors"] == 0
    assert summary["visual_quality_score"] is None
    assert summary["regeneration_frequency"] == 0
    assert len(list((tmp_path / "runtime/archive").glob("*/manifest.json"))) == 2
