# Routing evaluation (synthetic)

Positive class: counterfeit scan (`is_clone_scan`), not cloned serial. Genuine scans of a cloned serial still count as negatives here, which differs from pack-level rule evaluation. Threshold is the 99th percentile of validation scores from genuine serials; training uses only genuine serials. Labels are excluded from features.

| Detector | Precision | Recall | F1 |
|---|---:|---:|---:|
| isolation_forest | 0.5573 | 0.5817 | 0.5692 |
| rules | 0.6136 | 0.5378 | 0.5732 |
| union | 0.5568 | 0.5857 | 0.5709 |

Additional clone scans: 12; same-city: 0; additional genuine-scan alerts: 32. This tradeoff does not establish superiority over rules. No real-world data or field validation.

```json
{
  "seed": 2026,
  "features": [
    "prior_scans",
    "distinct_sites",
    "prior_dispenses",
    "hours_since_nearest_scan",
    "max_distance_km",
    "max_speed_kmh",
    "impossible_legs"
  ],
  "serial_counts": [
    1800,
    600,
    600
  ],
  "threshold": 0.6170537598058592,
  "auc": 0.8842045910707781,
  "average_precision": 0.4978641688055448,
  "isolation_forest": {
    "precision": 0.5572519083969466,
    "recall": 0.5816733067729084,
    "f1": 0.5692007797270955
  },
  "rules": {
    "precision": 0.6136363636363636,
    "recall": 0.5378486055776892,
    "f1": 0.5732484076433121
  },
  "union": {
    "precision": 0.5568181818181818,
    "recall": 0.5856573705179283,
    "f1": 0.570873786407767
  },
  "additional_clone_scans": 12,
  "additional_genuine_scan_alerts": 32,
  "same_city_additional_clone_scans": 0,
  "onnx_outputs": [
    "label",
    "scores",
    "score_samples"
  ],
  "model_bytes": 821552
}
```
