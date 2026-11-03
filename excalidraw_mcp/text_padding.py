import math


def required_container_size(shape: str, text_w: float, text_h: float) -> tuple[float, float]:
    """Minimum container dimensions that keep `text_w` x `text_h` inside `shape`."""
    if shape == "ellipse":
        min_size = math.hypot(text_w, text_h) + 40.0
        return min_size, min_size
    elif shape == "diamond":
        return text_w * 1.6 + 48.0, text_h * 1.6 + 40.0
    else:
        return text_w + 36.0, text_h + 28.0
