import io
import logging
import platform
from .base import Generation, ProviderError

log = logging.getLogger(__name__)


class LocalProvider:
    """Runs SDXL locally on CPU, CUDA or Apple Silicon MPS; no cloud API key."""
    name = "local"

    def __init__(self, settings):
        self.settings = settings
        self.pipeline = None
        self.torch = None

    @property
    def model(self):
        return self.settings.local_model

    def _load_pipeline(self):
        if self.pipeline is not None:
            return
        try:
            import torch
            from diffusers import StableDiffusionXLPipeline
        except ImportError as exc:
            raise ProviderError(
                "local_model_dependencies",
                "Install the optional local image-generation dependencies for the selected device.",
            ) from exc
        device = self.settings.local_device
        if device == "auto":
            if platform.system() == "Darwin" and torch.backends.mps.is_available():
                device = "mps"
            elif torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"
        if device == "mps" and (platform.system() != "Darwin" or not torch.backends.mps.is_available()):
            raise ProviderError("local_acceleration_unavailable", "The MPS device is available only to a native Apple Silicon process.")
        if device == "cuda" and not torch.cuda.is_available():
            raise ProviderError("local_acceleration_unavailable", "The CUDA device is unavailable in this environment.")
        try:
            dtype = torch.float32 if device == "cpu" else torch.float16
            pipeline = StableDiffusionXLPipeline.from_pretrained(
                self.settings.local_model,
                dtype=dtype,
                variant="fp16" if device != "cpu" or self.settings.local_files_only else None,
                use_safetensors=True,
                cache_dir=str(self.settings.local_model_cache),
                local_files_only=self.settings.local_files_only,
            )
            pipeline.to(device)
            pipeline.enable_attention_slicing()
            pipeline.vae.enable_slicing()
        except Exception as exc:
            log.exception("Could not load local image model %s", self.settings.local_model)
            raise ProviderError(
                "local_model_load",
                "Could not load the local image model. Check the first-download internet connection and available disk space.",
            ) from exc
        self.pipeline = pipeline
        self.torch = torch
        self.device = device

    def generate(self, design):
        self._load_pipeline()
        s = self.settings
        seed = int(design["variation"]["seed"])
        negative = (
            "blurry, low detail, distorted stadium, impossible structure, malformed roof, "
            "broken perspective, duplicate buildings, text, lettering, logo, watermark, collage"
        )
        try:
            result = self.pipeline(
                prompt=design.get("local_prompt") or design["prompt"],
                negative_prompt=negative,
                width=s.local_width,
                height=s.local_height,
                num_inference_steps=s.local_steps,
                guidance_scale=s.local_guidance,
                generator=self.torch.Generator(device="cpu").manual_seed(seed),
            )
            image = result.images[0]
            data = io.BytesIO()
            image.save(data, format="PNG")
        except Exception as exc:
            log.exception("Local image generation failed for model %s", self.model)
            raise ProviderError(
                "local_generation_failed",
                "The local model could not generate this image. Try again or lower the local image dimensions.",
            ) from exc
        return Generation(data.getvalue(), {
            "provider": self.name, "model": self.model, "device": self.device, "seed": seed,
            "width": s.local_width, "height": s.local_height, "steps": s.local_steps,
            "is_mock": False,
        })
