"""Create or restore a verified directory snapshot. Stop the backend first."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.storage import verify_archive


def snapshot(source: Path, destination: Path):
    source, destination = source.resolve(), destination.resolve()
    if destination.exists() or source == destination or source in destination.parents:
        raise ValueError("Destination must be a new directory outside the source")
    if not (source / "stadium.sqlite3").is_file():
        raise ValueError("Source database not found")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (source / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Stop the backend before backup or restore")
        temp = Path(tempfile.mkdtemp(prefix="stadium-snapshot-", dir=destination.parent))
        try:
            with sqlite3.connect(source / "stadium.sqlite3") as src, sqlite3.connect(temp / "stadium.sqlite3") as dst:
                src.backup(dst)
                integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise ValueError("Database integrity check failed")
                rows = dst.execute("SELECT id,payload FROM jobs WHERE status='completed'").fetchall()
            if (source / "archive").exists():
                shutil.copytree(source / "archive", temp / "archive")
            for job_id, payload in rows:
                if verify_archive(temp, job_id) != json.loads(payload):
                    raise ValueError("Archive metadata does not match the database")
            os.rename(temp, destination)
        except BaseException:
            shutil.rmtree(temp, ignore_errors=True)
            raise
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    count = snapshot(args.source, args.destination)
    print(f"Verified snapshot created: {args.destination} ({count} completed designs). API keys are not included.")
