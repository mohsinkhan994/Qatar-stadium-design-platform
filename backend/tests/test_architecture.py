import pytest
from app.domain.catalog import QUESTIONS
from app.domain.design import build_design, validate_answers
from app.domain.architecture import DETAILS, FIELDS, ROOFS, SHAPES
from app.services.validation import evaluate_image, WEIGHTS
from app.providers.profiles import profile_settings
from app.core.config import Settings
from scripts.benchmark import cases
from test_backend import ANSWERS


@pytest.mark.parametrize("question", [q for q in QUESTIONS if q["id"] != "signature"])
def test_every_option_is_explicitly_mapped(question):
    key = question["id"]
    for option in question["options"]:
        answers = {
            **ANSWERS,
            key: [option["id"]] if question["type"] == "multiple" else option["id"],
        }
        design = build_design(answers, 42)
        assert {c["id"] for c in design["constraints"]} == set(ANSWERS)
        if key in DETAILS:
            assert DETAILS[key][option["id"]] in design["prompt"]
        elif key == "use":
            assert FIELDS[option["id"]] in design["prompt"]
        elif key == "shape":
            assert SHAPES[option["id"]] in design["prompt"]
        elif key == "roof":
            assert ROOFS[option["id"]] in design["prompt"]
        else:
            assert option["label"] in design["prompt"]


def test_track_camera_and_solar_priority():
    d = build_design(
        {**ANSWERS, "use": "athletics", "roof": "open", "setting": "sea"}, 9
    )
    assert "eight marked lanes" in d["prompt"]
    assert "entire eight-lane oval track" in d["variation"]["camera"]
    assert "coastline" in d["variation"]["camera"]
    assert "outside the uncovered bowl" in d["prompt"]


def test_validation_is_unavailable_without_pixels_evaluator():
    assert evaluate_image(None, b"image", {})["overall_score"] is None


@pytest.mark.parametrize(
    "critical,score,status",
    [(True, 90, "passed"), (False, 100, "failed"), (True, 84, "failed")],
)
def test_independent_critical_gate(critical, score, status):
    class Evaluator:
        def evaluate(self, image, design):
            assert image == b"actual image bytes"
            return {
                "criteria": dict.fromkeys(WEIGHTS, score),
                "critical_constraints_passed": critical,
            }

    assert evaluate_image(Evaluator(), b"actual image bytes", {})["status"] == status


def test_invalid_evaluator_scores_are_rejected():
    class Bad:
        def evaluate(self, *args):
            return {"criteria": dict.fromkeys(WEIGHTS, float("nan"))}

    with pytest.raises(ValueError):
        evaluate_image(Bad(), b"pixels", {})


def test_benchmark_matrix_and_seed_reproducibility():
    matrix = cases()
    assert len(matrix) == 50
    assert len({str(c["answers"]) for c in matrix}) == 50
    for c in matrix:
        validate_answers(c["answers"], complete=True, allow_free_text=True)
        assert build_design(c["answers"], c["seed"]) == build_design(
            c["answers"], c["seed"]
        )


def test_profiles_do_not_increase_sampling_steps():
    for profile in ("fast_preview", "balanced", "high_quality"):
        assert profile_settings(Settings(inference_profile=profile)).local_steps == 16


def test_conflicting_track_envelope_requires_confirmation():
    from app.domain.design import compatibility

    notes = compatibility(
        {**ANSWERS, "use": "athletics", "shape": "rectangular", "roof": "translucent"}
    )
    assert {"track_inside_shape", "track_roof_visibility"} <= {n["code"] for n in notes}


def test_multiselect_order_and_free_text_sanitization():
    from app.domain.design import InputError

    a = validate_answers(ANSWERS, complete=True)
    b = validate_answers(
        {**ANSWERS, "materials": list(reversed(ANSWERS["materials"]))}, complete=True
    )
    assert build_design(a, 42) == build_design(b, 42)
    with pytest.raises(InputError):
        validate_answers(
            {**ANSWERS, "signature": {"mode": "text", "text": "Entrance\x00"}},
            allow_free_text=True,
        )
    custom = validate_answers(
        {
            **ANSWERS,
            "signature": {"mode": "text", "text": "  Branching tree entrance  "},
        },
        allow_free_text=True,
    )
    design = build_design(custom, 42)
    assert design["signature"] == "Branching tree entrance"
    assert "signature entrance" in design["variation"]["camera"]


def test_local_visual_evaluator_receives_remaining_deadline():
    from app.services.validation import evaluate_image, WEIGHTS

    class Evaluator:
        def evaluate_with_timeout(self, image, design, timeout):
            assert image == b"pixels"
            assert timeout == 1.25
            return {
                "criteria": dict.fromkeys(WEIGHTS, 90),
                "critical_constraints_passed": True,
            }

    result = evaluate_image(Evaluator(), b"pixels", {}, timeout=1.25)
    assert result["status"] == "passed"
