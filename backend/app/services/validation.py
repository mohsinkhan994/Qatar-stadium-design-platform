"""Optional image evaluator contract. No prompt-based or fabricated scores."""

from typing import Protocol
import math

WEIGHTS = {
    "stadium_purpose": 25,
    "shape_and_roof": 20,
    "location_and_style": 20,
    "signature_feature": 15,
    "materials": 10,
    "landscaping": 10,
}


class ImageEvaluator(Protocol):
    def evaluate(self, image: bytes, design: dict) -> dict:
        """Analyze image pixels and return criteria, critical flag and missing features."""


def evaluate_image(evaluator, image, design, threshold=85, timeout=None):
    if evaluator is None:
        return {
            "status": "unavailable",
            "overall_score": None,
            "critical_constraints_passed": None,
            "recommend_regeneration": False,
        }
    bounded = getattr(evaluator, "evaluate_with_timeout", None)
    raw = (
        bounded(image, design, timeout)
        if bounded and timeout is not None
        else evaluator.evaluate(image, design)
    )
    values = raw["criteria"]
    if set(values) != set(WEIGHTS) or any(
        type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 100
        for v in values.values()
    ):
        raise ValueError("Invalid visual evaluation criteria")
    if type(raw["critical_constraints_passed"]) is not bool:
        raise ValueError("Evaluator must explicitly assess critical constraints")
    missing = raw.get("missing_features", [])
    if not isinstance(missing, list) or any(
        not isinstance(v, str) or len(v) > 500 for v in missing
    ):
        raise ValueError("Invalid missing features")
    score = sum(values[k] * w for k, w in WEIGHTS.items()) / 100
    passed = raw["critical_constraints_passed"] and score >= threshold
    return {
        "status": "passed" if passed else "failed",
        "overall_score": round(score, 2),
        "critical_constraints_passed": raw["critical_constraints_passed"],
        "criteria": values,
        "missing_features": missing,
        "recommend_regeneration": not raw["critical_constraints_passed"],
        "evaluator": type(evaluator).__name__,
    }


class LocalCommandEvaluator:
    """A configured local vision program reads JSON stdin and emits JSON stdout.

    The program must inspect image_path pixels, not merely score the supplied text.
    No evaluator weights or external API are installed or called by this adapter.
    """

    def __init__(self, command, timeout=30):
        self.command = command
        self.timeout = timeout

    def evaluate(self, image, design):
        return self.evaluate_with_timeout(image, design, self.timeout)

    def evaluate_with_timeout(self, image, design, timeout):
        import json
        import subprocess
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory(prefix="stadium-evaluate-") as directory:
            path = Path(directory) / "image.png"
            path.write_bytes(image)
            request = {
                "image_path": str(path),
                "constraints": design.get("constraints", []),
                "signature": design["signature"],
                "criteria": WEIGHTS,
            }
            result = subprocess.run(
                self.command,
                input=json.dumps(request),
                text=True,
                capture_output=True,
                timeout=min(self.timeout, timeout),
                check=True,
            )
            return json.loads(result.stdout)
