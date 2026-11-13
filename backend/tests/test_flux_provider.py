import io
import json
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image

from app.core.config import Settings
from app.domain.design import build_design
from app.providers.flux import Flux3Provider
from app.providers import ProviderError, provider_for


@pytest.fixture
def design():
    return build_design({
        "use": "football", "capacity": "60000", "setting": "desert", "theme": "qatar", "style": "qatari",
        "shape": "oval", "roof": "solar", "materials": ["stone", "perforated_metal"], "palette": "ivory",
        "experience": "comfort", "innovation": "gardens", "technologies": ["ai_guidance", "digital_twin"],
        "environment": ["solar", "water", "passive"], "legacy": "community", "signature": {"mode": "surprise"},
    }, 42)


@pytest.fixture
def local_settings(tmp_path):
    return Settings(provider="local", local_device="mps", data_dir=tmp_path,
                    flux_mlx_model_path=tmp_path / "model", flux_mlx_python=tmp_path / "python")


def test_flux_caption_preserves_requirements(design):
    caption = design["flux_prompt"].lower()
    for term in ("60,000", "solar", "stone", "ivory", "oval", "water", "digital twin"):
        assert term in caption
    assert design["signature"].lower() in caption
    assert len(caption) > len(design["local_prompt"])


def test_native_bridge_uses_full_caption_and_offline_mode(monkeypatch, local_settings, design):
    from pathlib import Path
    monkeypatch.setattr("app.providers.flux.mlx_ready", lambda _: True)
    def run(command, **kwargs):
        request = json.loads(kwargs["input"])
        assert request["prompt"] == design["flux_prompt"]
        assert request["seed"] == 42
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert kwargs["timeout"] == local_settings.timeout
        assert command[0] == str(local_settings.flux_mlx_python)
        Image.new("RGB", (256, 256), "green").save(Path(request["output"]))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("app.providers.flux.subprocess.run", run)
    result = provider_for(local_settings).generate(design)
    assert Image.open(io.BytesIO(result.image)).size == (256, 256)
    assert result.metadata["device"] == "mlx-metal"
    assert not result.metadata["is_mock"]


@pytest.mark.parametrize("failure,code", [
    (subprocess.TimeoutExpired("flux", 1), "local_generation_timeout"),
    (OSError("missing runtime"), "local_model_dependencies"),
])
def test_native_errors_are_explicit(monkeypatch, local_settings, design, failure, code):
    monkeypatch.setattr("app.providers.flux.mlx_ready", lambda _: True)
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr("app.providers.flux.subprocess.run", fail)
    with pytest.raises(ProviderError) as error:
        Flux3Provider(local_settings).generate(design)
    assert error.value.code == code


def test_missing_model_does_not_fall_back(monkeypatch, local_settings, design):
    monkeypatch.setattr("app.providers.flux.mlx_ready", lambda _: False)
    with pytest.raises(ProviderError) as error:
        Flux3Provider(local_settings).generate(design)
    assert error.value.code == "flux_setup_required"


def test_cuda_uses_distilled_pipeline_without_extra_upsampler(monkeypatch, tmp_path, design):
    import sys
    calls = []
    class Pipeline:
        def load_components(self, **kwargs):
            calls.append(("load", kwargs))
        def to(self, device):
            calls.append(("device", device))
        def __call__(self, **kwargs):
            calls.append(("generate", kwargs))
            return [Image.new("RGB", (256, 256), "green")]
    pipeline = Pipeline()
    class Blocks:
        sub_blocks = {"prompt_upsampler": object()}
        def init_pipeline(self, model):
            assert "prompt_upsampler" not in self.sub_blocks
            return pipeline
    class ModularPipeline:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return SimpleNamespace(blocks=Blocks())
    class Generator:
        def __init__(self, device):
            assert device == "cpu"
        def manual_seed(self, seed):
            assert seed == 42
            return self
    monkeypatch.setattr("huggingface_hub.hf_hub_download", lambda *args, **kwargs: str(tmp_path / "modular_model_index.json"))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True), float32="fp32", bfloat16="bf16", Generator=Generator))
    monkeypatch.setitem(sys.modules, "diffusers", SimpleNamespace(ModularPipeline=ModularPipeline))
    provider = Flux3Provider(Settings(provider="local", local_device="cuda", data_dir=tmp_path))
    provider.generate(design)
    provider.generate(design)
    assert len([call for call in calls if call[0] == "load"]) == 1
    generation = next(call[1] for call in calls if call[0] == "generate")
    assert generation["prompt"] == design["flux_prompt"]
    assert generation["num_inference_steps"] == 16
    assert "negative_prompt" not in generation


def test_runtime_python_keeps_virtualenv_symlink(monkeypatch, tmp_path):
    runtime = tmp_path / "venv" / "bin" / "python"
    runtime.parent.mkdir(parents=True)
    target = tmp_path / "system-python"
    target.touch()
    runtime.symlink_to(target)
    monkeypatch.setenv("FLUX_MLX_PYTHON", str(runtime))
    assert Settings.from_env().flux_mlx_python == runtime
    assert Settings.from_env().flux_mlx_python != target
