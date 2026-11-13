"""Local FLUX 3 Klein: isolated MLX on Mac, Diffusers on NVIDIA servers."""

import io
import time
from contextlib import nullcontext
import logging
import platform
import tempfile
from pathlib import Path

from .base import Generation, ProviderError

log = logging.getLogger(__name__)


class Flux3Provider:
    name = "local"

    def __init__(self, settings):
        from .profiles import profile_settings

        settings = profile_settings(settings)
        self.settings = settings
        import threading

        self.lock = threading.RLock()
        self.pipeline = None
        from .mlx_session import MLXSession

        self.mlx = MLXSession(settings)

    @property
    def model(self):
        return self.settings.local_model

    @property
    def uses_mlx(self):
        return self.settings.local_device == "mps" or (
            self.settings.local_device == "auto" and platform.system() == "Darwin"
        )

    def generate(self, design):
        return self.generate_with_timeout(design, self.settings.timeout)

    def generate_with_timeout(self, design, timeout):
        with self.lock:
            return self._generate(design, timeout)

    def _generate(self, design, timeout):
        s = self.settings
        started = time.monotonic()
        runtime_metadata = {}
        prompt = design["flux_prompt"]
        seed = int(design["variation"]["seed"])
        if self.uses_mlx:
            if not mlx_ready(s):
                raise ProviderError(
                    "flux_setup_required",
                    "Run scripts/setup_flux.sh to prepare FLUX 3 Klein first.",
                )
            with tempfile.TemporaryDirectory(prefix="stadium-flux-") as directory:
                output = Path(directory) / "image.png"
                request = {
                    "model_path": str(s.flux_mlx_model_path),
                    "prompt": prompt,
                    "seed": seed,
                    "width": s.local_width,
                    "height": s.local_height,
                    "steps": s.local_steps,
                    "output": str(output),
                    "reference": design.get("reference", {}).get("path"),
                    "timeout": timeout,
                }
                runtime_metadata = self.mlx.generate(request)
                try:
                    data = output.read_bytes()
                except OSError as exc:
                    raise ProviderError(
                        "local_generation_failed", "Image output is missing."
                    ) from exc
            device = "mlx-metal"
        else:
            data = self._generate_diffusers(prompt, seed, design.get("reference"))
            device = self.device
            runtime_metadata = self.runtime_metadata
        return Generation(
            data,
            {
                "provider": self.name,
                "model": self.model,
                "device": device,
                "width": s.local_width,
                "height": s.local_height,
                "steps": s.local_steps,
                "seed": seed,
                "quantization": 4 if self.uses_mlx else None,
                "profile": s.inference_profile,
                "backend": "mlx" if self.uses_mlx else "diffusers",
                "precision": "q4"
                if self.uses_mlx
                else ("bfloat16" if device == "cuda" else "float32"),
                "generation_duration_seconds": round(time.monotonic() - started, 3),
                "guidance": None,
                "prompt_version": design["prompt_version"],
                "is_mock": False,
                **runtime_metadata,
            },
        )

    def close(self):
        with self.lock:
            self.mlx.close()
            self.pipeline = None

    def _generate_diffusers(self, prompt, seed, reference=None):
        import torch
        from diffusers import ModularPipeline
        from huggingface_hub import hf_hub_download

        s = self.settings
        device = (
            "cuda"
            if s.local_device == "auto" and torch.cuda.is_available()
            else s.local_device
        )
        if device == "cuda" and not torch.cuda.is_available():
            raise ProviderError(
                "local_acceleration_unavailable", "The CUDA device is unavailable."
            )
        if device == "auto":
            device = "cpu"
        self.device = device
        if (
            device == "cuda"
            and not getattr(torch.cuda, "is_bf16_supported", lambda: True)()
        ):
            raise ProviderError(
                "local_acceleration_unavailable",
                "This FLUX checkpoint requires a BF16-capable CUDA device.",
            )
        try:
            cold = self.pipeline is None
            if device == "cuda" and hasattr(torch.cuda, "reset_peak_memory_stats"):
                torch.cuda.reset_peak_memory_stats()
            if self.pipeline is None:
                config_path = Path(
                    hf_hub_download(
                        self.model,
                        "modular_model_index.json",
                        cache_dir=str(s.local_model_cache),
                        local_files_only=s.local_files_only,
                    )
                ).parent
                blocks = ModularPipeline.from_pretrained(
                    str(config_path), local_files_only=True
                ).blocks
                # Our questionnaire is expanded into a full caption in build_design.
                blocks.sub_blocks.pop("prompt_upsampler")
                pipe = blocks.init_pipeline(str(config_path))
                pipe.load_components(
                    dtype={
                        "vae": torch.float32,
                        "default": torch.bfloat16
                        if device == "cuda"
                        else torch.float32,
                    },
                    cache_dir=str(s.local_model_cache),
                    local_files_only=s.local_files_only,
                )
                pipe.to(device)
                self.pipeline = pipe
            from PIL import Image

            extra = {}
            if reference:
                with Image.open(reference["path"]) as source:
                    extra["image"] = source.convert("RGB").copy()
            with getattr(torch, "inference_mode", nullcontext)():
                image = self.pipeline(
                    **extra,
                    prompt=prompt,
                    width=s.local_width,
                    height=s.local_height,
                    num_inference_steps=s.local_steps,
                    generator=torch.Generator(device="cpu").manual_seed(seed),
                    output="images",
                )[0]
            output = io.BytesIO()
            image.save(output, format="PNG")
            self.runtime_metadata = {
                "cold_start": cold,
                "peak_memory_bytes": torch.cuda.max_memory_allocated()
                if device == "cuda" and hasattr(torch.cuda, "max_memory_allocated")
                else None,
            }
            return output.getvalue()
        except Exception as exc:
            log.exception("FLUX 3 local pipeline failed")
            raise ProviderError(
                "local_generation_failed",
                "Could not run FLUX 3. Check model access, cached weights and GPU memory.",
            ) from exc


def mlx_ready(settings):
    return (
        platform.system() == "Darwin"
        and settings.flux_mlx_python.is_file()
        and (settings.flux_mlx_python.parent / "mflux-generate-flux3").is_file()
        and (settings.flux_mlx_model_path / ".stadium-ready").is_file()
    )


def flux_configured(settings):
    if settings.local_device == "mps" or (
        settings.local_device == "auto" and platform.system() == "Darwin"
    ):
        return mlx_ready(settings)
    if (
        settings.local_files_only
        and not (settings.local_model_cache / ".stadium-cuda-ready").is_file()
    ):
        return False
    try:
        import torch
        from diffusers.modular_pipelines.flux3 import Flux3AutoBlocks  # noqa: F401
    except ImportError:
        return False
    return settings.local_device in {"cpu", "auto"} or (
        settings.local_device == "cuda" and torch.cuda.is_available()
    )
