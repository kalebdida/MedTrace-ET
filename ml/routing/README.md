# Routing anomaly experiment

Run `python ml/routing/train_isolation_forest.py` from the repository root after installing `ml/requirements.txt`. Source: the backend's seeded synthetic Ethiopian distribution simulator. Regenerate with `cd backend && python -m evaluation.simulate`. Defaults: 3,000 serials, 10% cloned, seed 2026. The script splits serials 60/20/20, fits 100 trees only on genuine training serials, and calibrates the anomaly threshold on genuine validation serials. No test labels tune the threshold.

Inputs, in exact order: prior_scans, distinct_sites, prior_dispenses, hours_since_nearest_scan, max_distance_km, max_speed_kmh, impossible_legs. Missing nearest-scan hours become 9999. No labels, site IDs, serial IDs, or rule decisions enter training. See results/README.md for the scan-level comparison with rules, including extra false alarms and same-city results. A cloned pack's genuine scan is a negative in this evaluation, unlike the simulator's pack-level evaluation.

`model.onnx` is under 1 MB. Export uses skl2onnx, requiring only the already-installed ONNX Runtime and NumPy at inference, not pickle or scikit-learn. Output `score_samples` matches scikit-learn within 1e-5 on 100 rows. It is a normality score: negate it to obtain the anomaly score and compare with the threshold in results/metrics.json.

Proposed integration (not implemented): form a float32 array of shape (1,7) from travel_features in the above order, invoke ONNX Runtime CPU, and raise `ROUTING_ANOMALY` with severity `warning` when `-score_samples > threshold`. Do not issue a critical clone alert based only on this experiment. Keep deterministic rules and log model version, score and threshold for auditing. The current backend verdict does not call this model.
