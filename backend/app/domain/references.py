"""Operator-curated local reference manifest. No remote downloads or visitor paths."""

import hashlib
import json
from pathlib import Path
from PIL import Image

CATEGORIES = {
    "athletics",
    "football",
    "multi_sport",
    "circular",
    "oval",
    "rectangular",
    "sculptural",
}


def select_reference(manifest, answers, seed):
    if manifest is None:
        return None
    manifest = Path(manifest).resolve()
    entries = json.loads(manifest.read_text())
    candidates = []
    for entry in entries:
        if (
            entry.get("category") not in CATEGORIES
            or not entry.get("license")
            or not entry.get("source")
        ):
            raise ValueError(
                "Reference assets require a supported category, license and source"
            )
        path = (manifest.parent / entry["file"]).resolve()
        if not path.is_relative_to(manifest.parent):
            raise ValueError("Reference path escapes asset directory")
        if entry["category"] == answers["use"]:
            candidates.append((0, entry, path))
        elif entry["category"] == answers["shape"] and answers["use"] in entry.get(
            "compatible_uses", []
        ):
            candidates.append((1, entry, path))
    if not candidates:
        return None
    priority = min(c[0] for c in candidates)
    candidates = [c for c in candidates if c[0] == priority]
    _, entry, path = candidates[seed % len(candidates)]
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Reference exceeds size limit")
    with Image.open(path) as image:
        if image.width * image.height > 16_000_000:
            raise ValueError("Reference dimensions too large")
        image.verify()
    return {
        **entry,
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
