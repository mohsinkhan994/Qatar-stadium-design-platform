#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv-flux/bin/python ]; then
    .venv/bin/python -m venv .venv-flux
fi
# Reuse installed backend packages read-only; ML packages with different versions
# are installed into this child environment and cannot replace backend packages.
.venv/bin/python - <<'PYTHON'
from pathlib import Path
root = Path.cwd()
child = next((root / ".venv-flux/lib").glob("python*/site-packages"))
parent = next((root / ".venv/lib").glob("python*/site-packages"))
(child / "stadium_shared.pth").write_text(str(parent) + "\n")
PYTHON
export HF_HUB_CACHE="$PWD/models/flux3-hub"
.venv-flux/bin/python -m pip install --timeout 120 --retries 10 -r requirements-flux-mac.txt
# Authenticate with hf auth login first and accept the model conditions on Hugging Face.
.venv-flux/bin/python scripts/download_flux.py
printf '\nFLUX 3 Klein is ready. Start with ./scripts/run.sh mps\n'
