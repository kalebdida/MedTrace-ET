"""CPU-only packaging embedding inference; no PyTorch dependency."""

import hashlib
import io
import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps


def preprocess(image):
    image = (
        ImageOps.exif_transpose(image)
        .convert("RGB")
        .resize((224, 224), Image.Resampling.BILINEAR)
    )
    array = np.asarray(image, dtype=np.float32) / 255.0
    array = (array - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
        [0.229, 0.224, 0.225], dtype=np.float32
    )
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None])


class Verifier:
    def __init__(self, directory):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        model = directory / "model.onnx"
        self.session = ort.InferenceSession(
            str(model), sess_options=options, providers=["CPUExecutionProvider"]
        )
        with np.load(directory / "references.npz", allow_pickle=False) as refs:
            self.references = {key: refs[key].copy() for key in refs.files}
        self.model_version = (
            "synthetic-demo-" + hashlib.sha256(model.read_bytes()).hexdigest()[:12]
        )

    def embedding(self, image):
        return self.session.run(None, {"image": preprocess(image)})[0][0]

    def similarity(self, image: bytes, gtin: str):
        if gtin not in self.references:
            return None
        with Image.open(io.BytesIO(image)) as decoded:
            vector = self.embedding(decoded)
        reference = self.references[gtin]
        cosine = float(
            np.dot(vector, reference)
            / max(np.linalg.norm(vector) * np.linalg.norm(reference), 1e-12)
        )
        return float(np.clip((cosine + 1) / 2, 0, 1))


def load():
    return Verifier(Path(os.environ.get("VISUAL_MODEL_DIR", Path(__file__).parent)))
