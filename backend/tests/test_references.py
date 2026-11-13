import json
from PIL import Image
import pytest
from app.domain.references import select_reference, CATEGORIES
from test_backend import ANSWERS


def test_reference_manifest_requires_provenance_and_stays_local(tmp_path):
    manifest = tmp_path / "references.json"
    image = tmp_path / "football.png"
    Image.new("RGB", (64, 64), "green").save(image)
    entry = {
        "category": "football",
        "file": "football.png",
        "source": "Internally drawn geometry",
        "license": "Owned by project",
    }
    manifest.write_text(json.dumps([entry]))
    selected = select_reference(manifest, ANSWERS, 42)
    assert selected["path"] == str(image)
    assert len(selected["sha256"]) == 64
    assert select_reference(None, ANSWERS, 42) is None
    assert (
        select_reference(
            manifest, {**ANSWERS, "use": "entertainment", "shape": "wave"}, 42
        )
        is None
    )
    manifest.write_text(json.dumps([{**entry, "file": "../outside.png"}]))
    with pytest.raises(ValueError, match="escapes"):
        select_reference(manifest, ANSWERS, 42)
    manifest.write_text(json.dumps([{**entry, "license": ""}]))
    with pytest.raises(ValueError, match="license"):
        select_reference(manifest, ANSWERS, 42)


def test_all_requested_reference_categories():
    assert CATEGORIES == {
        "athletics",
        "football",
        "multi_sport",
        "circular",
        "oval",
        "rectangular",
        "sculptural",
    }


def test_shape_reference_cannot_override_sport(tmp_path):
    manifest = tmp_path / "references.json"
    Image.new("RGB", (64, 64), "green").save(tmp_path / "shape.png")
    entry = {
        "category": "oval",
        "file": "shape.png",
        "source": "Project",
        "license": "Owned",
        "compatible_uses": ["football"],
    }
    manifest.write_text(json.dumps([entry]))
    assert select_reference(manifest, {**ANSWERS, "use": "athletics"}, 1) is None
    assert select_reference(manifest, ANSWERS, 1)["category"] == "oval"
