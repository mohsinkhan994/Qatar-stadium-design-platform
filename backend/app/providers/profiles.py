"""Resolution profiles; distilled sampling stays at the verified 16-step baseline."""

PROFILES = {
    "fast_preview": (768, 512, 16),
    "balanced": (1024, 576, 16),
    "high_quality": (1344, 768, 16),
}


def profile_settings(settings):
    from dataclasses import replace

    if settings.inference_profile == "balanced":
        return settings
    width, height, steps = PROFILES[settings.inference_profile]
    return replace(settings, local_width=width, local_height=height, local_steps=steps)
