"""Provision offline weights: quantized MLX package or Diffusers CUDA package."""
import os
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import argparse
from pathlib import Path
from huggingface_hub import snapshot_download, hf_hub_download

parser = argparse.ArgumentParser()
parser.add_argument("--cuda", action="store_true", help="Download the Diffusers package for the Linux server")
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
patterns = ["LICENSE.md", "NOTICE.md", "config.json", "manifest.json", "text_encoder/*"]
patterns += (["modular_model_index.json", "transformer/*", "vae/*"] if args.cuda
             else ["model.safetensors", "ae.safetensors"])
if not args.cuda:
    path = snapshot_download("mflux-community/flux-3-image-klein-mflux-q4",
                             revision="79c0034de040c460e9685bf0127f40af042a2abe",
                             local_dir=str(root / "models/flux3-image-klein-q4"), max_workers=4)
    for name in ("LICENSE.md", "NOTICE.md"):
        hf_hub_download("black-forest-labs/flux-3-image-klein", name,
                        revision="09561231f44e41381c461caf53d5452005a60ac9", local_dir=path)
    (Path(path) / ".stadium-ready").touch()
    print("Quantized Mac model ready:", path)
    raise SystemExit(0)
path = snapshot_download("black-forest-labs/flux-3-image-klein", cache_dir=str(root / "models/flux3-hub"),
                         allow_patterns=patterns, max_workers=4)
(root / "models/flux3-hub/.stadium-cuda-ready").touch()
print("Model cache ready:", path)
