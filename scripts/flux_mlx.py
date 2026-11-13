"""Private serial JSON-line bridge. Model weights stay resident between requests."""

import contextlib
import json
import sys
import time
import traceback


def main():
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux3.variants import Flux3Klein, Flux3KleinEdit
    import mlx.core as mx

    model = None
    model_path = None
    editing = False
    serving = "--serve" in sys.argv
    requests = sys.stdin if serving else [sys.stdin.read()]
    for line in requests:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                started = time.monotonic()
                cold = (
                    model is None
                    or model_path != request["model_path"]
                    or editing != bool(request.get("reference"))
                )
                if cold:
                    model = None
                    mx.clear_cache()
                    editing = bool(request.get("reference"))
                    model_type = Flux3KleinEdit if editing else Flux3Klein
                    model = model_type(
                        model_config=ModelConfig.flux3_image_klein(),
                        model_path=request["model_path"],
                    )
                    model_path = request["model_path"]
                mx.reset_peak_memory()
                extra = {"image_paths": [request["reference"]]} if editing else {}
                image = model.generate_image(
                    **extra,
                    prompt=request["prompt"],
                    seed=request["seed"],
                    width=request["width"],
                    height=request["height"],
                    num_inference_steps=request["steps"],
                )
                image.save(path=request["output"])
                metadata = {
                    "cold_start": cold,
                    "scheduler": "Flux3FlowMapScheduler",
                    "duration_seconds": time.monotonic() - started,
                    "peak_memory_bytes": mx.get_peak_memory(),
                    "precision": "quantized-4-bit weights / runtime mixed precision",
                }
                mx.clear_cache()
            if serving:
                print(json.dumps({"ok": True, "metadata": metadata}), flush=True)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            if not serving:
                raise
            print(json.dumps({"ok": False}), flush=True)
            model = None


if __name__ == "__main__":
    main()
