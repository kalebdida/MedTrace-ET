"""Serial-disjoint isolation forest; labels never enter the seven-feature tensor."""

import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_recall_fscore_support,
    roc_curve,
    precision_recall_curve,
)
from skl2onnx import to_onnx
import onnxruntime as ort
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

FEATURES = [
    "prior_scans",
    "distinct_sites",
    "prior_dispenses",
    "hours_since_nearest_scan",
    "max_distance_km",
    "max_speed_kmh",
    "impossible_legs",
]
ROOT = Path(__file__).resolve().parent


def metrics(y, pred):
    p, r, f, _ = precision_recall_fscore_support(
        y, pred, average="binary", zero_division=0
    )
    return {"precision": float(p), "recall": float(r), "f1": float(f)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--data",
        type=Path,
        default=ROOT.parents[1] / "backend/evaluation/data/scan_features.csv",
    )
    p.add_argument("--seed", type=int, default=2026)
    a = p.parse_args()
    df = pd.read_csv(a.data)
    serials = np.array(sorted(df.serial.unique()))
    np.random.default_rng(a.seed).shuffle(serials)
    train, val, test = np.split(
        serials, [int(0.6 * len(serials)), int(0.8 * len(serials))]
    )
    masks = [df.serial.isin(s) for s in [train, val, test]]
    X = (
        df[FEATURES]
        .fillna({"hours_since_nearest_scan": 9999})
        .to_numpy(dtype=np.float32)
    )
    if not np.isfinite(X).all():
        raise ValueError("Unexpected missing or nonfinite features")
    model = IsolationForest(
        n_estimators=100, max_samples=256, random_state=a.seed, n_jobs=2
    )
    model.fit(X[masks[0] & (df.serial_cloned == 0)])
    score = -model.score_samples(X)
    threshold = float(np.quantile(score[masks[1] & (df.serial_cloned == 0)], 0.99))
    held = df[masks[2]].copy()
    y = held.is_clone_scan.to_numpy()
    s = score[masks[2]]
    pred = s > threshold
    baseline = held.rule_flagged.to_numpy().astype(bool)
    result = {
        "seed": a.seed,
        "features": FEATURES,
        "serial_counts": [len(train), len(val), len(test)],
        "threshold": threshold,
        "auc": float(roc_auc_score(y, s)),
        "average_precision": float(average_precision_score(y, s)),
        "isolation_forest": metrics(y, pred),
        "rules": metrics(y, baseline),
        "union": metrics(y, pred | baseline),
        "additional_clone_scans": int(((y == 1) & pred & ~baseline).sum()),
        "additional_genuine_scan_alerts": int(((y == 0) & pred & ~baseline).sum()),
        "same_city_additional_clone_scans": int(
            ((y == 1) & pred & ~baseline & (held.scenario == "same_city")).sum()
        ),
    }
    for name, coords in [
        ("roc", roc_curve(y, s)[:2]),
        ("pr", precision_recall_curve(y, s)[:2][::-1]),
    ]:
        plt.plot(*coords)
        plt.xlabel("False positive rate" if name == "roc" else "Recall")
        plt.ylabel("True positive rate" if name == "roc" else "Precision")
        plt.tight_layout()
        plt.savefig(ROOT / f"results/{name}.png")
        plt.close()
    onnx = to_onnx(
        model,
        X[:1],
        target_opset={"": 17, "ai.onnx.ml": 3},
        options={id(model): {"score_samples": True}},
    )
    (ROOT / "model.onnx").write_bytes(onnx.SerializeToString())
    session = ort.InferenceSession(
        str(ROOT / "model.onnx"), providers=["CPUExecutionProvider"]
    )
    outputs = session.run(None, {session.get_inputs()[0].name: X[:100]})
    names = [x.name for x in session.get_outputs()]
    idx = names.index("score_samples")
    np.testing.assert_allclose(
        outputs[idx].ravel(), model.score_samples(X[:100]), atol=1e-5
    )
    result["onnx_outputs"] = names
    result["model_bytes"] = (ROOT / "model.onnx").stat().st_size
    (ROOT / "results/metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    (ROOT / "results/splits.json").write_text(
        json.dumps(
            dict(train=train.tolist(), validation=val.tolist(), test=test.tolist()),
            indent=2,
        )
        + "\n"
    )
    lines = [
        "# Routing evaluation (synthetic)",
        "",
        "Positive class: counterfeit scan (`is_clone_scan`), not cloned serial. Genuine scans of a cloned serial still count as negatives here, which differs from pack-level rule evaluation. Threshold is the 99th percentile of validation scores from genuine serials; training uses only genuine serials. Labels are excluded from features.",
        "",
        "| Detector | Precision | Recall | F1 |",
        "|---|---:|---:|---:|",
    ]
    for key in ["isolation_forest", "rules", "union"]:
        lines.append(
            "| "
            + key
            + " | "
            + " | ".join(f"{result[key][m]:.4f}" for m in ["precision", "recall", "f1"])
            + " |"
        )
    lines += [
        "",
        "Additional clone scans: "
        + str(result["additional_clone_scans"])
        + "; same-city: "
        + str(result["same_city_additional_clone_scans"])
        + "; additional genuine-scan alerts: "
        + str(result["additional_genuine_scan_alerts"])
        + ". This tradeoff does not establish superiority over rules. No real-world data or field validation.",
        "",
        "```json",
        json.dumps(result, indent=2),
        "```",
    ]
    (ROOT / "results/README.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
