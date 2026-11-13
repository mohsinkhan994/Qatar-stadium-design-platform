"""One serial, persistent MLX subprocess, isolated from FastAPI dependencies."""

import json
import os
import selectors
import subprocess
import threading
import time

from app.core.config import ROOT
from .base import ProviderError


class MLXSession:
    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.log = None
        self.lock = threading.RLock()

    def close(self):
        with self.lock:
            process, self.process = self.process, None
            if process:
                try:
                    process.stdin.close()
                except OSError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                process.stdout.close()
            if self.log:
                self.log.close()
                self.log = None

    def generate(self, request):
        with self.lock:
            try:
                if self.process is None or self.process.poll() is not None:
                    self.close()
                    self.settings.data_dir.mkdir(parents=True, exist_ok=True)
                    self.log = (self.settings.data_dir / "flux-runtime.log").open("a")
                    env = {
                        **os.environ,
                        "HF_HUB_OFFLINE": "1",
                        "TRANSFORMERS_OFFLINE": "1",
                        "HF_HUB_CACHE": str(ROOT / "models/flux3-hub"),
                    }
                    self.process = subprocess.Popen(
                        [
                            str(self.settings.flux_mlx_python),
                            str(ROOT / "scripts/flux_mlx.py"),
                            "--serve",
                        ],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=self.log,
                        env=env,
                    )
                deadline = time.monotonic() + min(
                    self.settings.timeout, request.get("timeout", self.settings.timeout)
                )
                self.process.stdin.write((json.dumps(request) + "\n").encode())
                self.process.stdin.flush()
                response_bytes = bytearray()
                with selectors.DefaultSelector() as selector:
                    selector.register(self.process.stdout, selectors.EVENT_READ)
                    while b"\n" not in response_bytes:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(remaining):
                            raise ProviderError(
                                "local_generation_timeout",
                                "Image generation exceeded its time limit.",
                            )
                        chunk = os.read(self.process.stdout.fileno(), 4096)
                        if not chunk:
                            raise ValueError("Image runtime closed its output")
                        response_bytes.extend(chunk)
                        if len(response_bytes) > 65536:
                            raise ValueError(
                                "Image runtime response exceeded its limit"
                            )
                response = json.loads(response_bytes)
                if not isinstance(response, dict) or not response.get("ok"):
                    raise ProviderError(
                        "local_generation_failed",
                        "The local model could not complete this image.",
                    )
                metadata = response.get("metadata", {})
                if not isinstance(metadata, dict):
                    raise ValueError("Invalid image runtime metadata")
                return metadata
            except ProviderError:
                self.close()
                raise
            except (OSError, ValueError) as exc:
                self.close()
                raise ProviderError(
                    "local_model_dependencies",
                    "The isolated image runtime stopped unexpectedly.",
                ) from exc
