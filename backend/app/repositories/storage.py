import hashlib
import io
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Database:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "stadium.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, language TEXT NOT NULL, station TEXT NOT NULL,
                    answers TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL, error_code TEXT, error_message TEXT,
                    UNIQUE(session_id, request_id)
                );
                CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_job_per_session ON jobs(session_id)
                    WHERE status IN ('queued','generating','saving');
            """)

    @contextmanager
    def connect(self, immediate=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            if immediate:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def job(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def update_job(self, job_id, status, payload=None, error_code=None, error_message=None):
        with self.connect(immediate=True) as db:
            if payload is not None:
                db.execute("UPDATE jobs SET payload=? WHERE id=?", (encode(payload), job_id))
            db.execute("UPDATE jobs SET status=?,updated_at=?,error_code=?,error_message=? WHERE id=?",
                       (status, now(), error_code, error_message, job_id))

    def claim(self):
        with self.connect(immediate=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='generating',updated_at=? WHERE id=?", (now(), row["id"]))
                return dict(row)

    def image_exists(self, pixel_hash):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM jobs WHERE status='completed'").fetchall()
        return any(json.loads(row["payload"]).get("image", {}).get("pixel_sha256") == pixel_hash for row in rows)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare_image(raw):
    if len(raw) > 40 * 1024 * 1024:
        raise ValueError("Image exceeds 40 MB limit")
    with Image.open(io.BytesIO(raw)) as source:
        if source.width * source.height > 32_000_000 or min(source.size) < 64:
            raise ValueError("Invalid image dimensions")
        source.load()
        image = ImageOps.exif_transpose(source).convert("RGB")
    full = io.BytesIO()
    image.save(full, "PNG")
    small = image.copy()
    small.thumbnail((480, 320))
    thumb = io.BytesIO()
    small.save(thumb, "JPEG", quality=85)
    return full.getvalue(), thumb.getvalue(), {
        "width": image.width, "height": image.height, "mime_type": "image/png",
        "sha256": sha(full.getvalue()), "thumbnail_sha256": sha(thumb.getvalue()),
        "pixel_sha256": sha(str(image.size).encode() + image.tobytes()),
    }


def atomic_write(path, data):
    """fsync contents and directory before exposing a completed file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_archive(root, job_id, payload, full, thumb):
    folder = Path(root) / "archive" / job_id
    atomic_write(folder / "image.png", full)
    atomic_write(folder / "thumbnail.jpg", thumb)
    atomic_write(folder / "manifest.json", encode(payload).encode("utf-8"))
    return verify_archive(root, job_id)


def verify_archive(root, job_id):
    folder = Path(root) / "archive" / job_id
    payload = json.loads((folder / "manifest.json").read_text())
    if payload["archive_reference"] != job_id:
        raise ValueError("Archive identity mismatch")
    for name, field in [("image.png", "sha256"), ("thumbnail.jpg", "thumbnail_sha256")]:
        if sha((folder / name).read_bytes()) != payload["image"][field]:
            raise ValueError("Archive checksum mismatch")
    return payload


def recover(db):
    """Recover finished files, but never silently repeat a potentially billed API call."""
    with db.connect() as conn:
        rows = conn.execute("SELECT id FROM jobs WHERE status IN ('generating','saving')").fetchall()
    for row in rows:
        try:
            payload = verify_archive(db.directory, row["id"])
            db.update_job(row["id"], "completed", payload)
        except (OSError, ValueError, KeyError):
            db.update_job(row["id"], "interrupted", error_code="interrupted",
                          error_message="Generation was interrupted. Review before submitting a new job; the provider may have charged the previous request.")
