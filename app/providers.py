"""Provider adapters. No cloud request is made unless explicitly configured."""
import base64
import io
import logging
import platform
import random
from dataclasses import dataclass

import httpx
from PIL import Image, ImageDraw

log = logging.getLogger(__name__)


class ProviderError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class Generation:
    image: bytes
    metadata: dict


def decode_image(value):
    if not isinstance(value, str) or len(value) > 56 * 1024 * 1024:
        raise ProviderError("invalid_image", "Provider returned invalid image data.")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ProviderError("invalid_image", "Provider returned invalid image data.") from exc


class MockProvider:
    name = "mock"
    model = "schematic-test-v1"

    def generate(self, design):
        # This fixture is intentionally labelled and cannot be mistaken for AI output.
        rng = random.Random(design["variation"]["seed"])
        image = Image.new("RGB", (1024, 768), "#e7edf0")
        draw = ImageDraw.Draw(image)
        colour = tuple(rng.randint(55, 170) for _ in range(3))
        x, y = rng.randint(120, 200), rng.randint(170, 230)
        draw.ellipse((x, y, 1024-x, 650), fill=colour, outline="#334155", width=8)
        draw.ellipse((x+60, y+45, 964-x, 580), fill="#f8fafc")
        draw.rectangle((390, 310, 630, 500), fill="#54856b", outline="white", width=3)
        draw.line((390, 405, 630, 405), fill="white", width=2)
        draw.text((40, 40), "TEST SCHEMATIC - NOT AI GENERATED", fill="#17212e", font_size=30)
        draw.text((40, 90), design["title"], fill="#17212e", font_size=24)
        draw.text((40, 700), "Development fixture. Does not implement all selected design features.", fill="#17212e", font_size=20)
        data = io.BytesIO()
        image.save(data, "PNG")
        return Generation(data.getvalue(), {"provider": self.name, "model": self.model, "is_mock": True})


class CloudProvider:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def post(self, url, headers, body):
        try:
            with httpx.Client(timeout=httpx.Timeout(self.settings.timeout, connect=15), transport=self.transport,
                              follow_redirects=False) as client:
                response = client.post(url, headers=headers, json=body)
            if response.status_code in (401, 403):
                raise ProviderError("provider_access", "Provider authentication or model access failed. Check server configuration.")
            if response.status_code == 429:
                raise ProviderError("provider_limit", "Provider rate limit or billing quota reached. Try later after checking the account.")
            if response.status_code >= 400:
                raise ProviderError("provider_rejected", f"Provider rejected the request (HTTP {response.status_code}). Check model settings or try different choices.")
            return response.json(), response.headers.get("x-request-id")
        except httpx.TimeoutException as exc:
            raise ProviderError("provider_timeout", "Provider timed out. No automatic retry was made; the request may have been billed.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("provider_unavailable", "Could not reach the image provider. Check connectivity.") from exc
        except ValueError as exc:
            raise ProviderError("provider_response", "Provider returned an unreadable response.") from exc


class OpenAIProvider(CloudProvider):
    name = "openai"

    @property
    def model(self):
        return self.settings.openai_model

    def generate(self, design):
        s = self.settings
        data, request_id = self.post("https://api.openai.com/v1/images/generations",
            {"Authorization": f"Bearer {s.openai_api_key}"},
            {"model": self.model, "prompt": design["prompt"], "n": 1,
             "size": s.openai_size, "quality": s.openai_quality, "output_format": "png"})
        items = data.get("data", [])
        if not items or not items[0].get("b64_json"):
            raise ProviderError("no_image", "Provider did not return an image. The request may have been filtered.")
        return Generation(decode_image(items[0]["b64_json"]), {
            "provider": self.name, "model": self.model, "request_id": request_id,
            "usage": data.get("usage"), "requested_size": s.openai_size, "quality": s.openai_quality,
            "is_mock": False})


class GeminiProvider(CloudProvider):
    name = "gemini"

    @property
    def model(self):
        return self.settings.gemini_model

    def generate(self, design):
        s = self.settings
        data, request_id = self.post("https://generativelanguage.googleapis.com/v1beta/interactions",
            {"x-goog-api-key": s.gemini_api_key, "Api-Revision": "2026-05-20"},
            {"model": self.model, "input": design["prompt"],
             "response_format": {"type": "image", "mime_type": "image/png", "aspect_ratio": "3:2", "image_size": s.gemini_size}})
        # SDK convenience output_image and raw REST outputs are both handled.
        item = data.get("output_image")
        if not item:
            item = next((p for p in data.get("outputs", []) if p.get("type") == "image" and p.get("data")), None)
        if not item or not item.get("data"):
            raise ProviderError("no_image", "Provider did not return an image. The request may have been filtered.")
        return Generation(decode_image(item["data"]), {
            "provider": self.name, "model": self.model, "request_id": request_id or data.get("id"),
            "usage": data.get("usage"), "requested_size": s.gemini_size, "is_mock": False})


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


def provider_for(settings):
    if settings.provider == "local" and settings.local_engine == "flux3":
        from .flux_provider import Flux3Provider
        return Flux3Provider(settings)
    return {"mock": MockProvider, "openai": lambda: OpenAIProvider(settings),
            "gemini": lambda: GeminiProvider(settings),
            "local": lambda: LocalProvider(settings)}[settings.provider]()


def configured(settings):
    if settings.provider == "mock":
        return True
    if settings.provider == "openai":
        return bool(settings.openai_api_key)
    if settings.provider == "gemini":
        return bool(settings.gemini_api_key)
    if settings.provider == "local":
        if settings.local_engine == "flux3":
            from .flux_provider import flux_configured
            return flux_configured(settings)
        try:
            import torch
            from diffusers import StableDiffusionXLPipeline  # noqa: F401
            import transformers  # noqa: F401
            import safetensors  # noqa: F401
        except ImportError:
            return False
        if settings.local_device == "mps":
            return platform.system() == "Darwin" and torch.backends.mps.is_available()
        if settings.local_device == "cuda":
            return torch.cuda.is_available()
        if settings.local_device == "auto":
            return True
        return settings.local_device == "cpu"
    return False
