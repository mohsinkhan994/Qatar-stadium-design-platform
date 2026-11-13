import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from scripts.backup import snapshot
from test_backend import completed


def test_backup_restore_and_live_lock(tmp_path):
    settings = Settings(data_dir=tmp_path / "original", min_free_disk_mb=0)
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    with TestClient(create_app(settings)) as c:
        sid, result = completed(c)
        with pytest.raises(ValueError, match="Stop the backend"):
            snapshot(settings.data_dir, backup)
    assert snapshot(settings.data_dir, backup) == 1
    assert snapshot(backup, restored) == 1
    with TestClient(create_app(Settings(data_dir=restored, min_free_disk_mb=0))) as c:
        assert c.get(f"/api/v1/generations/{result['id']}").json()["status"] == "completed"
        assert c.post(f"/api/v1/sessions/{sid}/finish").status_code == 200
    with pytest.raises(ValueError, match="new directory"):
        snapshot(backup, restored)
