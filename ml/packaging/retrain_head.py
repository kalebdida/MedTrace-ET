"""Refit the embedding head on the frozen backbone, without PyTorch.

The committed ONNX model is a frozen ImageNet MobileNetV3-Small backbone
followed by one linear layer (Gemm "head") and L2 normalisation. This script
reads backbone features straight out of that ONNX graph, fits a new linear
head in closed form, and writes it back into the same graph. No pretrained
weights need downloading and no training framework is required.

Head: a Fisher-style projection. With the genuine capture scatter S_w (how
much genuine photos of one product vary: lighting, angle, focus) and the
defect scatter S_d (how far each synthetic defect moves features from its
product's genuine mean), solve S_d v = lambda (S_w + alpha I) v and keep the
top 127 directions. Genuine capture variation is suppressed and defect
directions amplified. Output dimension 0 is a constant B, so the cosine to a
product's reference falls as the projected deviation grows. Alpha and B are
chosen on the validation split only; the test split is touched once, at the
end, for the old-vs-new comparison.

    python ml/packaging/retrain_head.py   # after scripts/make_demo_dataset.py
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnx import numpy_helper
from PIL import Image
from sklearn.metrics import roc_auc_score

from augment import PACKAGE, ROOT, augment, dataset, preprocess

FEATURE = "/Flatten_output_0"  # backbone output feeding the head Gemm
DIMS = 128
EXTRA_GENUINE_VIEWS = 4  # extra hard-genuine views per training source


def session(model_bytes):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    return ort.InferenceSession(model_bytes, sess_options=options, providers=["CPUExecutionProvider"])


def feature_extractor(model):
    m = onnx.ModelProto()
    m.CopyFrom(model)
    del m.graph.output[:]
    m.graph.output.extend([onnx.helper.make_tensor_value_info(FEATURE, onnx.TensorProto.FLOAT, [1, 576])])
    return session(m.SerializeToString())


def with_head(model, weight, bias):
    m = onnx.ModelProto()
    m.CopyFrom(model)
    for init in m.graph.initializer:
        if init.name == "head.weight":
            init.CopyFrom(numpy_helper.from_array(weight.astype(np.float32), "head.weight"))
        elif init.name == "head.bias":
            init.CopyFrom(numpy_helper.from_array(bias.astype(np.float32), "head.bias"))
    return m


def embed(sess, images):
    return np.stack([sess.run(None, {"image": preprocess(im)})[0][0] for im in images])


def similarity(z, ref):
    z = z / np.linalg.norm(z, axis=1, keepdims=True)
    return np.clip((z @ (ref / np.linalg.norm(ref)) + 1) / 2, 0, 1)


def fit_head(x_gen, gtin_gen, x_def, gtin_def, alpha, scale):
    means = {g: x_gen[gtin_gen == g].mean(0) for g in np.unique(gtin_gen)}
    dev_g = x_gen - np.stack([means[g] for g in gtin_gen])
    dev_d = x_def - np.stack([means[g] for g in gtin_def])
    s_w = dev_g.T @ dev_g / len(dev_g)
    s_d = dev_d.T @ dev_d / len(dev_d)
    reg = s_w + alpha * np.trace(s_w) / len(s_w) * np.eye(len(s_w))
    # Whiten by reg, then take the leading eigenvectors of the whitened S_d.
    evals, evecs = np.linalg.eigh(reg)
    whiten = evecs @ np.diag(evals ** -0.5) @ evecs.T
    dvals, dvecs = np.linalg.eigh(whiten @ s_d @ whiten)
    proj = whiten @ dvecs[:, ::-1][:, : DIMS - 1]  # 576 x 127
    center = np.mean(list(means.values()), axis=0)
    spread = np.median(np.linalg.norm(dev_g @ proj, axis=1))
    weight = np.vstack([np.zeros(576), proj.T])
    bias = np.concatenate([[scale * spread], -proj.T @ center])
    return weight, bias


def scores(feats, gtins, refs, weight, bias):
    z = feats @ weight.T + bias
    return np.array([similarity(z[i : i + 1], refs[g])[0] for i, g in enumerate(gtins)])


def references(feats, gtins, weight, bias):
    z = feats @ weight.T + bias
    z = z / np.linalg.norm(z, axis=1, keepdims=True)
    refs = {}
    for g in np.unique(gtins):
        v = z[gtins == g].mean(0)
        refs[g] = v / np.linalg.norm(v)
    return refs


def summarise(y, s, val_genuine):
    """Thresholds from validation genuine scores only, as in evaluate.py."""
    mismatch = float(np.quantile(val_genuine, 0.01, method="lower"))
    pred = s < mismatch
    genuine = y == 0
    return {
        "auc": float(roc_auc_score(y, 1 - s)),
        "mismatch_below": mismatch,
        "test_genuine_false_alarm_rate": float(pred[genuine].mean()),
        "test_defect_recall": float(pred[~genuine].mean()),
        "false_alarms": f"{int(pred[genuine].sum())}/{int(genuine.sum())}",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, default=ROOT / "data/raw")
    p.add_argument("--seed", type=int, default=2026)
    a = p.parse_args()
    rng = np.random.default_rng(a.seed)

    rows = dataset(a.raw, a.seed)
    base = onnx.load(PACKAGE / "model.onnx")
    extract = feature_extractor(base)
    current = session(base.SerializeToString())

    feats = embed(extract, [Image.open(ROOT / r["path"]) for r in rows])
    gtin = np.array([r["gtin"] for r in rows])
    split = np.array([r["split"] for r in rows])
    label = np.array([r["label"] for r in rows])

    # Extra hard-genuine views of training sources (never of held-out sources).
    train_sources = sorted({(r["source"], r["gtin"]) for r in rows if r["split"] == "train"})
    views, view_gtin = [], []
    for source, g in train_sources:
        with Image.open(a.raw / source) as original:
            views += [augment(original, "genuine", rng) for _ in range(EXTRA_GENUINE_VIEWS)]
            view_gtin += [g] * EXTRA_GENUINE_VIEWS
    view_feats = embed(extract, views)

    train = split == "train"
    x_gen = np.vstack([feats[train & (label == 0)], view_feats])
    g_gen = np.concatenate([gtin[train & (label == 0)], view_gtin])
    x_def, g_def = feats[train & (label == 1)], gtin[train & (label == 1)]
    originals = {(r["source"]) for r in rows if r["split"] == "train" and r["defect"] == "genuine"}
    enroll_mask = np.array([r["split"] == "train" and r["defect"] == "genuine" and r["source"] in originals for r in rows])

    val, test = split == "validation", split == "test"
    best = None
    for alpha in (0.01, 0.03, 0.1, 0.3, 1.0):
        for scale in (1.0, 2.0, 4.0):
            w, b = fit_head(x_gen, g_gen, x_def, g_def, alpha, scale)
            refs = references(feats[enroll_mask], gtin[enroll_mask], w, b)
            s = scores(feats[val], gtin[val], refs, w, b)
            yv = label[val]
            mismatch = np.quantile(s[yv == 0], 0.01, method="lower")
            recall = float((s[yv == 1] < mismatch).mean())
            key = (recall, float(roc_auc_score(yv, 1 - s)))
            if best is None or key > best[0]:
                best = (key, alpha, scale, w, b, refs)
    (val_recall, val_auc), alpha, scale, w, b, refs = best
    print(f"chosen on validation: alpha={alpha} scale={scale} val_recall={val_recall:.3f} val_auc={val_auc:.4f}")

    # Old model on the same splits, for an honest comparison.
    old_z = np.stack([current.run(None, {"image": preprocess(Image.open(ROOT / r["path"]))})[0][0] for r in rows])
    old_refs = {}
    for g in np.unique(gtin):
        v = old_z[enroll_mask & (gtin == g)].mean(0)
        old_refs[g] = v / np.linalg.norm(v)
    old_s = np.array([similarity(old_z[i : i + 1], old_refs[g])[0] for i, g in enumerate(gtin)])
    new_s = scores(feats, gtin, refs, w, b)

    comparison = {
        "dataset": {
            "captures_per_product": int(sum(1 for r in rows if r["gtin"] == gtin[0] and r["defect"] == "genuine")),
            "validation_genuine": int((val & (label == 0)).sum()),
            "test_genuine": int((test & (label == 0)).sum()),
            "test_defects": int((test & (label == 1)).sum()),
        },
        "previous_head": summarise(label[test], old_s[test], old_s[val & (label == 0)]),
        "refit_head": summarise(label[test], new_s[test], new_s[val & (label == 0)]),
        "refit_params": {"alpha": alpha, "scale": scale, "extra_genuine_views": EXTRA_GENUINE_VIEWS},
    }
    print(json.dumps(comparison, indent=2))
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/head_comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")

    new, old = comparison["refit_head"], comparison["previous_head"]
    if new["test_genuine_false_alarm_rate"] <= old["test_genuine_false_alarm_rate"] and new["auc"] >= old["auc"] - 0.01:
        shutil.copy(PACKAGE / "model.onnx", ROOT / "results/previous_model.onnx")
        onnx.save(with_head(base, w, b), PACKAGE / "model.onnx")
        np.savez(PACKAGE / "references.npz", **refs)
        print("Installed the refit head. Run evaluate.py to recompute thresholds and metrics.")
    else:
        print("Refit head is not better on the test split; previous model kept.")


if __name__ == "__main__":
    main()
