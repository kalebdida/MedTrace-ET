import argparse
import numpy as np
import torch
import onnxruntime as ort
from common import ROOT, PACKAGE, load_model


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", default=ROOT / "checkpoint.pt")
    a = p.parse_args()
    torch.set_num_threads(2)
    torch.manual_seed(2026)
    model = load_model(a.checkpoint)
    x = torch.randn(1, 3, 224, 224)
    torch.onnx.export(
        model,
        x,
        str(PACKAGE / "model.onnx"),
        input_names=["image"],
        output_names=["embedding"],
        opset_version=17,
        dynamo=False,
    )
    session = ort.InferenceSession(
        str(PACKAGE / "model.onnx"), providers=["CPUExecutionProvider"]
    )
    errors = []
    for _ in range(5):
        x = torch.randn(1, 3, 224, 224)
        with torch.no_grad():
            expected = model(x).numpy()
        actual = session.run(None, {"image": x.numpy()})[0]
        np.testing.assert_allclose(actual, expected, atol=1e-4, rtol=0)
        errors.append(float(np.max(np.abs(actual - expected))))
    print("ONNX max absolute error:", max(errors))


if __name__ == "__main__":
    main()
