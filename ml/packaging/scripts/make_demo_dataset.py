"""Render fictional medicine boxes; never represents actual manufacturer packaging."""

import argparse
import io
from pathlib import Path
import random
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


def phone_capture(face, rng):
    """Simulate an independent handheld phone photo of the box face.

    Every capture differs in framing, angle, lighting, white balance, sensor
    noise, focus and JPEG compression, so genuine captures are not near-copies.
    """
    background = tuple(rng.randrange(60, 200) for _ in range(3))
    canvas = Image.new("RGB", (360, 360), background)
    scale = rng.uniform(0.80, 0.97)
    size = int(320 * scale)
    box = face.resize((size, size), Image.Resampling.BILINEAR).rotate(
        rng.uniform(-6, 6), resample=Image.Resampling.BICUBIC, expand=True, fillcolor=background
    )
    canvas.paste(box, ((360 - box.width) // 2 + rng.randrange(-12, 13), (360 - box.height) // 2 + rng.randrange(-12, 13)))
    k = 0.0006
    canvas = canvas.transform(
        canvas.size, Image.Transform.PERSPECTIVE,
        (1, rng.uniform(-0.03, 0.03), 0, rng.uniform(-0.03, 0.03), 1, 0, rng.uniform(-k, k), rng.uniform(-k, k)),
        Image.Resampling.BICUBIC, fillcolor=background,
    ).crop((20, 20, 340, 340))
    canvas = ImageEnhance.Brightness(canvas).enhance(rng.uniform(0.75, 1.2))
    canvas = ImageEnhance.Contrast(canvas).enhance(rng.uniform(0.85, 1.15))
    arr = np.asarray(canvas, dtype=np.float32) * np.array([rng.uniform(0.94, 1.06) for _ in range(3)])
    arr += np.random.default_rng(rng.randrange(2**32)).normal(0, rng.uniform(1.5, 5), arr.shape)
    canvas = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(rng.uniform(0, 0.9)))
    stream = io.BytesIO()
    canvas.save(stream, format="JPEG", quality=rng.randrange(70, 96))
    return Image.open(io.BytesIO(stream.getvalue())).convert("RGB")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("ml/packaging/data/raw"))
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--captures", type=int, default=60, help="independent captures per product")
    a = p.parse_args()
    rng = random.Random(a.seed)
    for i, gtin in enumerate(["09506000134352", "00000000000017", "00000000000024"]):
        folder = a.out / gtin / "genuine"
        folder.mkdir(parents=True, exist_ok=True)
        for j in range(a.captures):
            im = Image.new("RGB", (320, 320), "ivory")
            d = ImageDraw.Draw(im)
            color = [(25, 110, 170), (40, 140, 65), (160, 45, 90)][i]
            d.rectangle((8, 8, 312, 90), fill=color)
            d.text(
                (18, 25),
                f"DEMO MED {i + 1}",
                font=ImageFont.load_default(size=30),
                fill="white",
            )
            d.text(
                (18, 110),
                "FICTIONAL PACKAGING",
                font=ImageFont.load_default(size=20),
                fill="black",
            )
            d.text(
                (18, 150),
                f"{100 * (i + 1)} mg / 20 tablets",
                font=ImageFont.load_default(size=22),
                fill=color,
            )
            for k in range(5):
                d.text(
                    (18, 185 + k * 13),
                    "Sample text - not for medical use",
                    font=ImageFont.load_default(size=11),
                    fill="black",
                )
            d.rectangle((15, 260, 305, 307), outline="black", width=2)
            d.text(
                (22, 275),
                f"BATCH {rng.randrange(1000, 9999)} EXP 2030",
                font=ImageFont.load_default(size=17),
                fill="black",
            )
            phone_capture(im, rng).save(folder / f"capture-{j:02}.jpg", quality=95)


if __name__ == "__main__":
    main()
