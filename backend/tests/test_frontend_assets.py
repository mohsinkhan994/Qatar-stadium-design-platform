"""Exercise the static frontend as served by the native Mac backend."""
import posixpath
import re

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_frontend_entrypoint_and_module_graph(tmp_path, monkeypatch):
    # Launching outside the repository must not break static asset discovery.
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app(Settings(data_dir=tmp_path / "data", min_free_disk_mb=0))) as client:
        index = client.get("/")
        assert index.status_code == 200
        stylesheet = re.search(r'<link rel="stylesheet" href="([^"]+)"', index.text)[1]
        assert "text/css" in client.get(stylesheet).headers["content-type"]
        entry = re.search(r'<script type="module" src="([^"]+)"', index.text)[1]
        pending, visited = [entry], set()
        while pending:
            path = pending.pop()
            if path in visited:
                continue
            visited.add(path)
            response = client.get(path)
            assert response.status_code == 200, path
            assert "javascript" in response.headers["content-type"], path
            for dependency in re.findall(r"from\s+['\"]([^'\"]+)['\"]", response.text):
                pending.append(posixpath.normpath(posixpath.join(posixpath.dirname(path), dependency)))
        assert "/src/features/stadium/controller.js" in visited
        assert "/src/features/stadium/views.js" in visited
        assert "/src/api/client.js" in visited
