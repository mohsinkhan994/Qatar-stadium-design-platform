import os
import json
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: ROOT / "data")
    provider: str = "mock"
    station_id: str = "macbook-demo"
    admin_api_key: str = ""
    kiosk_api_key: str = ""
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    openai_api_key: str = ""
    openai_model: str = "gpt-image-1.5"
    openai_size: str = "1536x1024"
    openai_quality: str = "medium"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-nano-banana-2.1"
    gemini_size: str = "2K"
    local_engine: str = "flux3"
    local_model: str = "black-forest-labs/flux-3-image-klein"
    flux_mlx_python: Path = field(
        default_factory=lambda: ROOT / ".venv-flux/bin/python"
    )
    flux_mlx_model_path: Path = field(
        default_factory=lambda: ROOT / "models/flux3-image-klein-q4"
    )
    local_model_cache: Path = field(
        default_factory=lambda: ROOT / "models" / "huggingface"
    )
    local_device: str = "auto"
    local_files_only: bool = False
    local_width: int = 1024
    local_height: int = 576
    local_steps: int = 16
    local_guidance: float = 6.0
    timeout: float = 180
    max_pending_jobs: int = 8
    min_free_disk_mb: int = 512
    max_attempts: int = 2
    allow_free_text: bool = False
    validation_threshold: float = 85
    inference_profile: str = "balanced"
    reference_manifest: Path | None = None
    evaluator_command: tuple[str, ...] = ()
    perceptual_duplicate_distance: int = -1

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        evaluator_command = json.loads(os.getenv("VISUAL_EVALUATOR_COMMAND", "[]"))
        if not isinstance(evaluator_command, list) or any(
            not isinstance(arg, str) or not arg for arg in evaluator_command
        ):
            raise ValueError(
                "VISUAL_EVALUATOR_COMMAND must be a JSON array of command arguments"
            )
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", str(ROOT / "data")))
            .expanduser()
            .resolve(),
            evaluator_command=tuple(evaluator_command),
            perceptual_duplicate_distance=int(
                os.getenv("PERCEPTUAL_DUPLICATE_DISTANCE", "-1")
            ),
            reference_manifest=Path(os.environ["REFERENCE_MANIFEST"])
            .expanduser()
            .resolve()
            if os.getenv("REFERENCE_MANIFEST")
            else None,
            validation_threshold=float(os.getenv("VISUAL_VALIDATION_THRESHOLD", "85")),
            inference_profile=os.getenv("INFERENCE_PROFILE", "balanced"),
            provider=os.getenv("GENERATION_PROVIDER", "mock"),
            station_id=os.getenv("STATION_ID", "macbook-demo"),
            admin_api_key=os.getenv("ADMIN_API_KEY", ""),
            kiosk_api_key=os.getenv("KIOSK_API_KEY", ""),
            cors_origins=tuple(
                filter(
                    None,
                    os.getenv(
                        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
                    ).split(","),
                )
            ),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1.5"),
            openai_size=os.getenv("OPENAI_IMAGE_SIZE", "1536x1024"),
            openai_quality=os.getenv("OPENAI_IMAGE_QUALITY", "medium"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-nano-banana-2.1"),
            gemini_size=os.getenv("GEMINI_IMAGE_SIZE", "2K"),
            local_engine=os.getenv("LOCAL_IMAGE_ENGINE", "flux3"),
            local_model=os.getenv(
                "LOCAL_IMAGE_MODEL", "black-forest-labs/flux-3-image-klein"
            ),
            flux_mlx_python=Path(
                os.getenv("FLUX_MLX_PYTHON", str(ROOT / ".venv-flux/bin/python"))
            )
            .expanduser()
            .absolute(),
            flux_mlx_model_path=Path(
                os.getenv(
                    "FLUX_MLX_MODEL_PATH", str(ROOT / "models/flux3-image-klein-q4")
                )
            )
            .expanduser()
            .resolve(),
            local_model_cache=Path(
                os.getenv(
                    "LOCAL_IMAGE_MODEL_CACHE", str(ROOT / "models" / "huggingface")
                )
            )
            .expanduser()
            .resolve(),
            local_device=os.getenv("LOCAL_IMAGE_DEVICE", "auto").lower(),
            local_files_only=os.getenv("LOCAL_IMAGE_LOCAL_FILES_ONLY", "false").lower()
            == "true",
            local_width=int(os.getenv("LOCAL_IMAGE_WIDTH", "1024")),
            local_height=int(os.getenv("LOCAL_IMAGE_HEIGHT", "576")),
            local_steps=int(os.getenv("LOCAL_IMAGE_STEPS", "16")),
            local_guidance=float(os.getenv("LOCAL_IMAGE_GUIDANCE", "6.0")),
            timeout=float(os.getenv("GENERATION_TIMEOUT_SECONDS", "180")),
            max_pending_jobs=int(os.getenv("MAX_PENDING_JOBS", "8")),
            min_free_disk_mb=int(os.getenv("MIN_FREE_DISK_MB", "512")),
            max_attempts=int(os.getenv("MAX_GENERATION_ATTEMPTS", "2")),
            allow_free_text=os.getenv("ALLOW_FREE_TEXT", "false").lower() == "true",
        )

    def validate(self):
        if not -1 <= self.perceptual_duplicate_distance <= 8 or any(
            not isinstance(x, str) for x in self.evaluator_command
        ):
            raise ValueError("Invalid evaluator or duplicate configuration")
        if not 0 <= self.validation_threshold <= 100 or self.inference_profile not in {
            "fast_preview",
            "balanced",
            "high_quality",
        }:
            raise ValueError("Invalid quality configuration")
        if self.provider not in {"mock", "openai", "gemini", "local"}:
            raise ValueError(
                "GENERATION_PROVIDER must be mock, openai, gemini or local"
            )
        if self.local_engine not in {"flux3", "sdxl"}:
            raise ValueError("LOCAL_IMAGE_ENGINE must be flux3 or sdxl")
        if (
            self.local_engine == "flux3"
            and self.local_model != "black-forest-labs/flux-3-image-klein"
        ):
            raise ValueError(
                "FLUX 3 engine requires black-forest-labs/flux-3-image-klein"
            )
        if self.local_device not in {"auto", "cpu", "cuda", "mps"}:
            raise ValueError("LOCAL_IMAGE_DEVICE must be auto, cpu, cuda or mps")
        if (
            not 1 <= self.max_attempts <= 3
            or self.max_pending_jobs < 1
            or self.timeout <= 0
        ):
            raise ValueError("Invalid generation limits")
        if self.min_free_disk_mb < 0:
            raise ValueError("MIN_FREE_DISK_MB cannot be negative")
        if (
            not self.local_model
            or self.local_steps < 1
            or self.local_steps > 60
            or self.local_width < 256
            or self.local_height < 256
            or self.local_width % 64
            or self.local_height % 64
            or self.local_width * self.local_height > 1_500_000
            or self.local_guidance <= 0
        ):
            raise ValueError("Invalid local image model settings")
