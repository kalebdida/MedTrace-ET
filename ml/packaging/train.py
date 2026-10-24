"""Frozen ImageNet MobileNetV3-Small with contrastively trained 128-D head."""

import argparse
import random
import numpy as np
import torch
from PIL import Image
from common import ROOT, Network, dataset, preprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=__import__("pathlib").Path, default=ROOT / "data/raw")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--epochs", type=int, default=120)
    p.add_argument("--threads", type=int, default=2)
    a = p.parse_args()
    torch.set_num_threads(a.threads)
    torch.manual_seed(a.seed)
    random.seed(a.seed)
    np.random.seed(a.seed)
    torch.use_deterministic_algorithms(True)
    rows = dataset(a.raw, a.seed)
    model = Network(pretrained=True).eval()
    for param in model.features.parameters():
        param.requires_grad = False
    train = [r for r in rows if r["split"] == "train"]
    with torch.no_grad():
        features = torch.cat(
            [
                model.backbone(
                    torch.from_numpy(preprocess(Image.open(ROOT / r["path"])))
                )
                for r in train
            ]
        )
    positives = {
        g: [i for i, r in enumerate(train) if r["gtin"] == g and not r["label"]]
        for g in sorted({r["gtin"] for r in train})
    }
    optimizer = torch.optim.Adam(model.head.parameters(), lr=0.002)
    rng = random.Random(a.seed)
    for epoch in range(a.epochs):
        anchor = torch.tensor([rng.choice(positives[r["gtin"]]) for r in train])
        labels = torch.tensor([r["label"] for r in train])
        z = torch.nn.functional.normalize(model.head(features), dim=1)
        distance = (z[anchor] - z).square().sum(1).clamp_min(1e-8).sqrt()
        loss = (
            (1 - labels) * distance.square()
            + labels * torch.relu(1.2 - distance).square()
        ).mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    torch.save(
        {"state": model.state_dict(), "seed": a.seed, "epochs": a.epochs},
        ROOT / "checkpoint.pt",
    )
    print(f"Trained on {len(train)} images; final contrastive loss={loss.item():.6f}")


if __name__ == "__main__":
    main()
