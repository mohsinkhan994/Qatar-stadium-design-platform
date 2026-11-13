"""Local FLUX 3 Klein: isolated MLX on Mac, Diffusers on NVIDIA servers."""
import io
import json
import logging
import os
import platform
import subprocess
import tempfile
from pathlib import Path

from app.core.config import ROOT
from .base import Generation, ProviderError

log = logging.getLogger(__name__)


class Flux3Provider:
    name = "local"

    def __init__(self, settings):
        self.settings = settings
        self.pipeline = None

    @property
    def model(self):
        return self.settings.local_model

    @property
    def uses_mlx(self):
        return self.settings.local_device == "mps" or (
            self.settings.local_device == "auto" and platform.system() == "Darwin")

    def generate(self, design):
        s = self.settings
        prompt = design["flux_prompt"]
        seed = int(design["variation"]["seed"])
        if self.uses_mlx:
            if not mlx_ready(s):
                raise ProviderError("flux_setup_required", "Run scripts/setup_flux.sh to prepare FLUX 3 Klein first.")
            with tempfile.TemporaryDirectory(prefix="stadium-flux-") as directory:
                output = Path(directory) / "image.png"
                request = {"model_path": str(s.flux_mlx_model_path), "prompt": prompt,
                           "seed": seed, "width": s.local_width, "height": s.local_height,
                           "steps": s.local_steps, "output": str(output)}
                env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                       "HF_HUB_CACHE": str(ROOT / "models/flux3-hub")}
                try:
                    # A separate process keeps MLX dependencies and GPU allocations isolated.
                    s.data_dir.mkdir(parents=True, exist_ok=True)
                    with (s.data_dir / "flux-runtime.log").open("w+") as runtime_log:
                        result = subprocess.run(
                            [str(s.flux_mlx_python), str(ROOT / "scripts" / "flux_mlx.py")],
                            input=json.dumps(request), text=True, stdout=runtime_log, stderr=runtime_log,
                            timeout=s.timeout, env=env, check=False)
                    if result.returncode or not output.is_file():
                        raise ProviderError("local_generation_failed", "FLUX generation failed. Check the model setup and available memory.")
                    data = output.read_bytes()
                except subprocess.TimeoutExpired as exc:
                    raise ProviderError("local_generation_timeout", "FLUX generation exceeded its time limit. Try fewer steps or smaller dimensions.") from exc
                except OSError as exc:
                    raise ProviderError("local_model_dependencies", "The isolated FLUX runtime could not start. Run scripts/setup_flux.sh.") from exc
            device = "mlx-metal"
        else:
            data = self._generate_diffusers(prompt, seed)
            device = self.device
        return Generation(data, {"provider": self.name, "model": self.model, "device": device,
                                 "width": s.local_width, "height": s.local_height, "steps": s.local_steps,
                                 "seed": seed, "quantization": 4 if self.uses_mlx else None,
                                 "prompt_version": design["prompt_version"], "is_mock": False})

    def _generate_diffusers(self, prompt, seed):
        import torch
        from diffusers import ModularPipeline
        from huggingface_hub import hf_hub_download
        s = self.settings
        device = "cuda" if s.local_device == "auto" and torch.cuda.is_available() else s.local_device
        if device == "cuda" and not torch.cuda.is_available():
            raise ProviderError("local_acceleration_unavailable", "The CUDA device is unavailable.")
        if device == "auto":
            device = "cpu"
        self.device = device
        try:
            if self.pipeline is None:
                config_path = Path(hf_hub_download(
                    self.model, "modular_model_index.json", cache_dir=str(s.local_model_cache),
                    local_files_only=s.local_files_only)).parent
                blocks = ModularPipeline.from_pretrained(str(config_path), local_files_only=True).blocks
                # Our questionnaire is expanded into a full caption in build_design.
                blocks.sub_blocks.pop("prompt_upsampler")
                pipe = blocks.init_pipeline(str(config_path))
                pipe.load_components(dtype={"vae": torch.float32,
                                            "default": torch.bfloat16 if device == "cuda" else torch.float32},
                                     cache_dir=str(s.local_model_cache), local_files_only=s.local_files_only)
                pipe.to(device)
                self.pipeline = pipe
            image = self.pipeline(prompt=prompt, width=s.local_width, height=s.local_height,
                                  num_inference_steps=s.local_steps,
                                  generator=torch.Generator(device="cpu").manual_seed(seed), output="images")[0]
            output = io.BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
        except Exception as exc:
            log.exception("FLUX 3 local pipeline failed")
            raise ProviderError("local_generation_failed", "Could not run FLUX 3. Check model access, cached weights and GPU memory.") from exc


def mlx_ready(settings):
    return (platform.system() == "Darwin" and settings.flux_mlx_python.is_file()
            and (settings.flux_mlx_python.parent / "mflux-generate-flux3").is_file()
            and (settings.flux_mlx_model_path / ".stadium-ready").is_file())


def flux_configured(settings):
    if settings.local_device == "mps" or (settings.local_device == "auto" and platform.system() == "Darwin"):
        return mlx_ready(settings)
    if settings.local_files_only and not (settings.local_model_cache / ".stadium-cuda-ready").is_file():
        return False
    try:
        import torch
        from diffusers.modular_pipelines.flux3 import Flux3AutoBlocks  # noqa: F401
    except ImportError:
        return False
    return settings.local_device in {"cpu", "auto"} or (settings.local_device == "cuda" and torch.cuda.is_available())
