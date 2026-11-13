"""Private JSON/stdin bridge, executed only by the isolated .venv-flux runtime."""
import json
import sys

from mflux.models.common.config import ModelConfig
from mflux.models.flux3.variants import Flux3Klein


def main():
    request = json.load(sys.stdin)
    model = Flux3Klein(model_config=ModelConfig.flux3_image_klein(), model_path=request["model_path"])
    image = model.generate_image(prompt=request["prompt"], seed=request["seed"],
                                 width=request["width"], height=request["height"],
                                 num_inference_steps=request["steps"])
    image.save(path=request["output"])


if __name__ == "__main__":
    main()
