"""Exercise the real pipe lifecycle with a tiny CPU-only substitute child."""

import subprocess
import sys
import pytest
from app.core.config import Settings
from app.providers.mlx_session import MLXSession
from app.providers.base import ProviderError


def child_factory(monkeypatch, program):
    original = subprocess.Popen
    starts = []

    def start(command, **kwargs):
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        process = original([sys.executable, "-u", "-c", program], **kwargs)
        starts.append(process)
        return process

    monkeypatch.setattr("app.providers.mlx_session.subprocess.Popen", start)
    return starts


def test_two_requests_reuse_one_process_and_close(monkeypatch, tmp_path):
    starts = child_factory(
        monkeypatch,
        'import sys,json,os\nfor line in sys.stdin:\n print(json.dumps({"ok":True,"metadata":{"pid":os.getpid()}}),flush=True)',
    )
    session = MLXSession(Settings(data_dir=tmp_path, timeout=5))
    try:
        first = session.generate({})
        second = session.generate({})
        assert first["pid"] == second["pid"]
        assert len(starts) == 1
    finally:
        session.close()
    assert starts[0].poll() is not None
    assert session.process is None


def test_deadline_reaps_child(monkeypatch, tmp_path):
    starts = child_factory(monkeypatch, "import time; time.sleep(30)")
    session = MLXSession(Settings(data_dir=tmp_path, timeout=5))
    with pytest.raises(ProviderError, match="time limit"):
        session.generate({"timeout": 0.05})
    assert starts[0].poll() is not None
    assert session.process is None


def test_crashed_child_is_reaped(monkeypatch, tmp_path):
    starts = child_factory(monkeypatch, "import sys; sys.stdin.readline(); sys.exit(1)")
    session = MLXSession(Settings(data_dir=tmp_path, timeout=5))
    with pytest.raises(ProviderError):
        session.generate({})
    assert starts[0].poll() is not None


def test_partial_protocol_response_cannot_bypass_timeout(monkeypatch, tmp_path):
    starts = child_factory(
        monkeypatch,
        'import sys,time; sys.stdin.readline(); sys.stdout.write("{"); sys.stdout.flush(); time.sleep(30)',
    )
    session = MLXSession(Settings(data_dir=tmp_path, timeout=5))
    with pytest.raises(ProviderError, match="time limit"):
        session.generate({"timeout": 0.05})
    assert starts[0].poll() is not None
