from .base import Generation, ProviderError, decode_image
from .cloud import CloudProvider


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
