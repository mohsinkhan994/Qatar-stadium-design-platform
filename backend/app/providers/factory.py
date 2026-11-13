"""Provider selection and configuration checks."""
import platform
from .mock import MockProvider
from .openai import OpenAIProvider
from .gemini import GeminiProvider
from .sdxl import LocalProvider


def provider_for(settings):
    if settings.provider == "local" and settings.local_engine == "flux3":
        from .flux import Flux3Provider
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
            from .flux import flux_configured
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
