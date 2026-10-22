# Clone-detection evaluation

There is no public dataset of pharmaceutical serial scans in Ethiopia, so `simulate.py` generates a reproducible synthetic one from the assumptions below. It replays every scan through the production detector (`medtrace.velocity.assess_clone_risk`, the same code the Lambda runs) and measures how well cloned serials are caught.

```bash
cd backend
python -m evaluation.simulate                      # 3000 packs, 10% cloned, seed 2026
python -m evaluation.simulate --serials 10000 --clone-rate 0.05 --seed 1
```

Outputs:

- **`results.md`**: detection and false-alarm rates at speed limits from 60 to 300 km/h.
- **`data/scan_features.csv`**: one labelled row per scan, containing the same `travel_features` the backend stores on every audit record.

## Assumptions

| Aspect | Model |
|---|---|
| Geography | 14 Ethiopian cities (approximate centre coordinates); every site lies within 4 km of its city centre |
| Genuine journey | Importer in Addis Ababa → regional wholesaler (random city) → pharmacy (same city 70%, else a city within 300 km) → 0–2 shelf checks → dispensed (90%) → occasional re-check minutes later (5%) |
| Transport | Road distance = 1.3 × straight-line; trucks average 35–65 km/h plus 1–12 h loading; 5% of shipments from Addis to cities with airports go by express air freight, 5–12 h door to door |
| Dwell times | Wholesaler 0.5–21 days; shelf checks up to 10 days apart; dispensing up to 45 days after receipt |
| Phone GPS | 80% good fix (≈15 m error, honest accuracy); 17% network fix (0.1–1.5 km error, honest accuracy); **3% bad fix (2–5 km error while reporting 10–50 m)** |
| Cloning | 10% of serials are copied onto a batch of 1–4 counterfeit packs, released between 30 days before and 60 days after the genuine pack reaches its pharmacy, reaching shelves within 3 days of each other. 75% go to cities ≥ 100 km away, 25% to other pharmacies in the same city |

## Results

Full table: [`results.md`](results.md). Headline at the default 120 km/h limit:

- **91.7%** of cloned serials are flagged: 92.5% when copies go to other cities, 89.4% within the same city.
- **0.1%** of genuine packs are falsely flagged (4 of 2,687), and **98.6%** of alerts are real clones.
- Only **52%** of clones are flagged **before a counterfeit is dispensed**. Barcode and travel rules can only fire once a second copy of the serial is scanned, and the dispense rules (which catch most clones) often fire when the genuine pack turns up after a counterfeit has already been sold. Closing that gap is the job of the packaging model: it can reject a counterfeit pack on its **first** scan.
- **Choosing the limit:** dropping it below 100 km/h catches clones earlier but raises false alarms quickly (0.9% at 60 km/h). At or above 100 km/h, false alarms stay at about 0.1%.
- **False-alarm cause:** all 4 come from a pharmacist re-checking a pack at the same pharmacy minutes after dispensing it, while the phone reports a bad fix with a falsely small accuracy radius.

## Dataset for the routing-anomaly model

`data/scan_features.csv` has one row per scan, in time order per serial.

| Column | Use |
|---|---|
| `prior_scans`, `distinct_sites`, `prior_dispenses`, `hours_since_nearest_scan`, `max_distance_km`, `max_speed_kmh`, `impossible_legs` | **Features**: identical to the `travel_features` the backend stores, so a model trained here scores live scans without any conversion |
| `event_type`, `city`, `lat`, `lon`, `accuracy_m`, `scanned_at`, `site_id` | Context (usable for feature engineering) |
| `is_clone_scan`, `serial_cloned`, `scenario` | **Labels**, for evaluation only |
| `rule_flagged` | What the rule-based detector decided; the baseline to beat. Not a feature |

Use `is_clone_scan`/`serial_cloned` only to evaluate an unsupervised model such as Isolation Forest, never as inputs. Split train and test **by serial**, not by row, so scans of the same pack never land on both sides.

## Limitations

These numbers describe the detection logic under the stated assumptions. They are not measured field performance. Real distribution patterns, GPS quality and counterfeiter behaviour in Ethiopia will differ, and the parameters should be re-fitted once real scan data from pilot pharmacies (or EFDA) is available.
