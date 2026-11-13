"""Common image provider result and error contracts."""
import base64
from dataclasses import dataclass

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
