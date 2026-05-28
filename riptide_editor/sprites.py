from __future__ import annotations

from PIL import Image

from .formats import DatEntry


def read_sprite_frames(entry: DatEntry, palette: list[tuple[int, int, int]]) -> list[Image.Image]:
    data = entry.data
    if not data:
        return []
    pos = 0
    frame_count = data[pos]
    pos += 1
    frames: list[Image.Image] = []
    for _ in range(frame_count):
        if pos + 2 > len(data):
            break
        width = data[pos]
        height = data[pos + 1]
        pos += 2
        pixel_count = width * height
        if width <= 0 or height <= 0 or pos + pixel_count > len(data):
            break
        img = Image.new("RGBA", (width, height))
        rgba = []
        for value in data[pos:pos + pixel_count]:
            r, g, b = palette[value]
            a = 0 if value == 0 else 255
            rgba.append((r, g, b, a))
        img.putdata(rgba)
        frames.append(img)
        pos += pixel_count
    return frames
