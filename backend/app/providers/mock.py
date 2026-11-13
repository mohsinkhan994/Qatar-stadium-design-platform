import io
import random
from PIL import Image, ImageDraw
from .base import Generation


class MockProvider:
    name = "mock"
    model = "schematic-test-v1"

    def generate(self, design):
        # This fixture is intentionally labelled and cannot be mistaken for AI output.
        rng = random.Random(design["variation"]["seed"])
        image = Image.new("RGB", (1024, 768), "#e7edf0")
        draw = ImageDraw.Draw(image)
        colour = tuple(rng.randint(55, 170) for _ in range(3))
        x, y = rng.randint(120, 200), rng.randint(170, 230)
        draw.ellipse((x, y, 1024-x, 650), fill=colour, outline="#334155", width=8)
        draw.ellipse((x+60, y+45, 964-x, 580), fill="#f8fafc")
        draw.rectangle((390, 310, 630, 500), fill="#54856b", outline="white", width=3)
        draw.line((390, 405, 630, 405), fill="white", width=2)
        draw.text((40, 40), "TEST SCHEMATIC - NOT AI GENERATED", fill="#17212e", font_size=30)
        draw.text((40, 90), design["title"], fill="#17212e", font_size=24)
        draw.text((40, 700), "Development fixture. Does not implement all selected design features.", fill="#17212e", font_size=20)
        data = io.BytesIO()
        image.save(data, "PNG")
        return Generation(data.getvalue(), {"provider": self.name, "model": self.model, "is_mock": True})
