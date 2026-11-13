from .base import Generation, ProviderError, decode_image
from .cloud import CloudProvider


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
