"""Baut packaging/djsync.ico aus den SVG-Quellen in diesem Ordner.

Drei Varianten, damit das Icon auch klein lesbar bleibt:
  djsync.svg        64–256 px: Sync-Pfeile um eine Achtelnote
  djsync-small.svg  32–48 px: dieselbe Form mit dickeren Linien
  djsync-tiny.svg   16–24 px: nur die Note

Aufruf (im Projektordner):
  uv run --with pillow --with cairosvg python packaging/icon/build_ico.py
"""

import io
from pathlib import Path

import cairosvg
from PIL import Image

HERE = Path(__file__).parent
SOURCES = {
    16: "djsync-tiny.svg",
    20: "djsync-tiny.svg",
    24: "djsync-tiny.svg",
    32: "djsync-small.svg",
    40: "djsync-small.svg",
    48: "djsync-small.svg",
    64: "djsync.svg",
    128: "djsync.svg",
    256: "djsync.svg",
}


def render(name: str, size: int) -> Image.Image:
    png = cairosvg.svg2png(url=str(HERE / name), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> None:
    images = {size: render(name, size) for size, name in SOURCES.items()}
    target = HERE.parent / "djsync.ico"
    images[256].save(
        target,
        sizes=[(s, s) for s in SOURCES],
        append_images=[img for s, img in images.items() if s != 256],
    )
    print(f"{target} geschrieben ({', '.join(map(str, SOURCES))} px)")


if __name__ == "__main__":
    main()
