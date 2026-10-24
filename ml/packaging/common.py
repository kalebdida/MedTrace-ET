import io
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import torch
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT.parents[1] / "backend/visual_model"
DEFECTS = ["hue", "ink_bleed", "reprint", "stamp", "resolution", "halftone"]


class Network(torch.nn.Module):
    def __init__(self, pretrained=False):
        super().__init__()
        base = mobilenet_v3_small(
            weights=MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
        )
        self.features = base.features
        self.pool = torch.nn.AdaptiveAvgPool2d(1)
        self.head = torch.nn.Linear(576, 128)

    def backbone(self, x):
        return self.pool(self.features(x)).flatten(1)

    def forward(self, x):
        return torch.nn.functional.normalize(self.head(self.backbone(x)), dim=1)


def augment(im, kind, rng):
    im = ImageOps.exif_transpose(im).convert("RGB").resize((224, 224))
    if kind == "genuine":
        im = ImageEnhance.Brightness(im).enhance(rng.uniform(0.85, 1.15))
        im = im.rotate(
            rng.uniform(-3, 3), resample=Image.Resampling.BILINEAR, fillcolor="ivory"
        )
        # Mild camera angle/shear and blur, labelled genuine.
        im = im.transform(
            im.size,
            Image.Transform.AFFINE,
            (1, rng.uniform(-0.025, 0.025), 0, 0, 1, 0),
            Image.Resampling.BILINEAR,
        )
        return im.filter(ImageFilter.GaussianBlur(rng.uniform(0, 0.4)))
    if kind == "hue":
        hsv = np.array(im.convert("HSV"))
        hsv[:, :, 0] = (hsv[:, :, 0].astype(int) + rng.integers(35, 90)) % 256
        return Image.fromarray(hsv, "HSV").convert("RGB")
    if kind == "ink_bleed":
        region = (
            im.crop((8, 72, 216, 177))
            .filter(ImageFilter.GaussianBlur(0.6))
            .filter(ImageFilter.MinFilter(3))
        )
        im.paste(region, (8, 72))
        return im
    if kind == "reprint":
        stream = io.BytesIO()
        im.save(stream, format="JPEG", quality=5)
        stream.seek(0)
        return Image.open(stream).convert("RGB")
    if kind == "stamp":
        region = im.crop((10, 182, 214, 215)).resize((140, 24))
        im.paste("ivory", (10, 182, 214, 215))
        im.paste(region, (55, 190))
        return im
    if kind == "resolution":
        return im.resize((40, 40)).resize((224, 224), Image.Resampling.NEAREST)
    if kind == "halftone":
        arr = np.array(im)
        arr[::3, ::3] = rng.integers(0, 100)
        return Image.fromarray(arr)
    raise ValueError(kind)


def dataset(raw, seed):
    rng = np.random.default_rng(seed)
    rows = []
    generated = ROOT / "data/generated"
    generated.mkdir(parents=True, exist_ok=True)
    for folder in sorted(raw.glob("*/genuine")):
        files = sorted(folder.glob("*.jpg"))
        if len(files) < 10:
            raise ValueError(f"{folder}: need at least 10 independent captures")
        order = rng.permutation(len(files))
        n = len(files)
        for rank, index in enumerate(order):
            split = (
                "train"
                if rank < int(n * 0.6)
                else "validation"
                if rank < int(n * 0.8)
                else "test"
            )
            source = files[index]
            with Image.open(source) as original:
                for kind in ["genuine"] + DEFECTS:
                    path = generated / f"{folder.parent.name}-{source.stem}-{kind}.png"
                    augment(original, kind, rng).save(path)
                    rows.append(
                        dict(
                            path=str(path.relative_to(ROOT)),
                            source=str(source.relative_to(raw)),
                            gtin=folder.parent.name,
                            split=split,
                            defect=kind,
                            label=int(kind != "genuine"),
                        )
                    )
    (ROOT / "data/manifest.json").write_text(json.dumps(rows, indent=2))
    return rows


def load_model(checkpoint):
    obj = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model = Network()
    model.load_state_dict(obj["state"])
    model.eval()
    return model
