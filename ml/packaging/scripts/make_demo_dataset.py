"""Render fictional medicine boxes; never represents actual manufacturer packaging."""

import argparse
from pathlib import Path
import random
from PIL import Image, ImageDraw, ImageFont


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("ml/packaging/data/raw"))
    p.add_argument("--seed", type=int, default=2026)
    a = p.parse_args()
    rng = random.Random(a.seed)
    for i, gtin in enumerate(["09506000134352", "00000000000017", "00000000000024"]):
        folder = a.out / gtin / "genuine"
        folder.mkdir(parents=True, exist_ok=True)
        for j in range(15):
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
            im.save(folder / f"capture-{j:02}.jpg", quality=95)


if __name__ == "__main__":
    main()
