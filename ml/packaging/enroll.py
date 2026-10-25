"""Enroll only training-source originals, never held-out captures."""

import argparse, json
import numpy as np
import onnxruntime as ort
from PIL import Image
from augment import ROOT, PACKAGE, preprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=__import__("pathlib").Path, default=ROOT / "data/raw")
    a = p.parse_args()
    rows = json.loads((ROOT / "data/manifest.json").read_text())
    refs = {}
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(
        str(PACKAGE / "model.onnx"),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    for gtin in sorted({r["gtin"] for r in rows}):
        sources = sorted(
            {r["source"] for r in rows if r["split"] == "train" and r["gtin"] == gtin}
        )
        vec = np.mean(
            [
                session.run(None, {"image": preprocess(Image.open(a.raw / s))})[0][0]
                for s in sources
            ],
            axis=0,
        )
        refs[gtin] = vec / np.linalg.norm(vec)
    np.savez(PACKAGE / "references.npz", **refs)


if __name__ == "__main__":
    main()
