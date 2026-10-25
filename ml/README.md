# Reproducible ML experiments

Python 3.13, CPU only. These are synthetic demonstrations, not validated counterfeit detectors. On the held-out synthetic test split the packaging model flags 1 of 36 genuine captures (2.8%) and catches 216 of 216 synthetic defects (AUC 0.9999); see packaging/results/head_comparison.json for the before/after comparison. Do not interpret successful smoke fixtures or high synthetic AUC as clinical or field reliability.

## Reproduce

From the repository root, in a separate virtual environment:

```sh
python3.13 -m venv .ml-venv
. .ml-venv/bin/activate
pip install -r ml/requirements.txt
python ml/packaging/scripts/make_demo_dataset.py        # 60 simulated phone captures per product
# Either the original PyTorch path (needs torchvision ImageNet weights):
#   python ml/packaging/train.py --seed 2026 --epochs 120 --threads 2 && python ml/packaging/export_onnx.py && python ml/packaging/enroll.py
# or the current, PyTorch-free head refit on the committed ONNX backbone:
python ml/packaging/retrain_head.py
python ml/packaging/evaluate.py
(cd backend && python -m evaluation.simulate)
python ml/routing/train_isolation_forest.py --seed 2026
```

In sandboxes set TORCH_HOME and MPLCONFIGDIR to writable cache locations. All stochastic training/splitting uses seed 2026; CPU floating-point results may vary slightly across hardware/library builds. The generated source manifest and evaluation split lists are saved. Generated raw/augmented images and the training checkpoint are ignored; committed ONNX files and reference embeddings allow inference without training or network downloads. Retraining changes artifacts: rerun evaluation and update SAM's two threshold environment variables from backend/visual_model/thresholds.json together.

## Packaging model

A shared ImageNet MobileNetV3-Small backbone (frozen, evaluation-mode batch normalization) maps each image to 576 features. A trainable linear head produces L2-normalized 128-dimensional embeddings, trained with contrastive loss (positive same-product genuine pairs, negative synthetic defects, distance margin 1.2). Freezing the backbone permits fast CPU training on tiny data. Similarity is `(cosine + 1)/2` against the normalized mean of each GTIN's enrolled genuine embeddings.

**Current head (refit).** `retrain_head.py` keeps the same frozen backbone and replaces only the linear head, without PyTorch: it reads 576-d backbone features from the committed ONNX graph and fits a Fisher-style projection that suppresses genuine capture variation (lighting, angle, focus, noise, JPEG) and amplifies defect directions (generalized eigenvectors of defect vs. genuine scatter, ridge-regularized), plus a constant output dimension so cosine falls as the projected deviation grows. Regularization and scale are chosen on validation only. On the same held-out test images the previous contrastive head reached AUC 0.947 and caught 73% of defects at its validation threshold; the refit head reaches AUC 0.9999 and catches 100%, with the same 1/36 genuine false alarm. The training set also changed: `make_demo_dataset.py` now simulates independent handheld phone captures (framing, ±6° rotation, perspective, brightness/contrast, white balance, sensor noise, focus blur, JPEG 70–95) and produces 60 per product instead of 15 near-identical renders, so calibration uses 36 validation genuine captures instead of 9.

`backend/visual_model` loads a roughly 4 MB ONNX file and reference vectors with CPU ONNX Runtime; inference never imports torch. Model version includes the ONNX content hash. VISUAL_MODEL_DIR overrides the artifact directory. Unknown GTIN returns None; malformed images raise and are handled by the existing backend's graceful-error path. Deployment sets VISUAL_MODEL_MODULE and calibrated thresholds. Only three fictional GTINs are enrolled; real unregistered products return no_reference.

See packaging/results/README.md for ROC, confusion matrix, per-defect breakdown, accuracy/precision/recall/F1, thresholds and measured latency. Current warm CPU p50/p95 is about 3.6/3.8 ms on the development host, not measured Lambda latency; cold startup and the 2 GB Lambda memory ceiling need deployment validation. CPU thread count is capped at two. The 512 MB infrastructure setting may need increasing after measuring CloudWatch Max Memory Used. No GPU is needed.

Thresholds use validation-only genuine quantiles corresponding to a 1% mismatch false-alarm target and 95% genuine acceptance target. 36 genuine calibration captures are still too few to substantiate a 1% target; the lower 1% quantile is effectively the validation minimum. Because the model is calibrated on phone-style captures, a perfectly clean digital render of the same design scores lower (about 0.85, below the mismatch threshold): domain shift matters, and real deployments must calibrate on real phone photos. The untouched test set exposes lighting/pose sensitivity. Collect independent real captures and counterfeit examples, enlarge calibration, evaluate by physical pack and product, and obtain expert review before treating results as authenticity evidence.

## Routing model

See routing/README.md and routing/results/README.md. The Isolation Forest improves recall modestly but adds false alerts and no additional same-city detections in this split. It is exported but deliberately not wired into backend verdicts.

## Provenance and licences

Pretrained weights: torchvision MobileNet_V3_Small_Weights.IMAGENET1K_V1, official URL https://download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth (torchvision verifies the published hash prefix). ImageNet training data has its own usage terms; PyTorch's software licence does not grant rights to the original images. We do not redistribute ImageNet images. The ONNX model contains derived pretrained weights; review upstream weight/data terms for intended use.

Libraries: PyTorch and torchvision (BSD-3-Clause); NumPy, SciPy, pandas, scikit-learn (BSD-3-Clause); Pillow (MIT-CMU/HPND); ONNX (Apache-2.0); ONNX Runtime (MIT); skl2onnx (Apache-2.0); matplotlib (PSF-based licence). Refer to the installed distributions for full notices and bundled dependency licences. Demo artwork is generated by this project's script using Pillow's bundled default font, not collected from the web. Phone photographs must be supplied with permission. Routing data comes solely from backend/evaluation/simulate.py.

## Validation

Install backend/requirements-dev.txt and run `cd backend && python -m pytest -q`. Real-model tests exercise score thresholds, unknown GTIN, malformed image handling, EXIF orientation, and a mocked full scan → packaging mismatch → audit → SNS flow. Export verification compares PyTorch and ONNX on five fixed-seed random tensors with absolute tolerance 1e-4. Runtime models are committed directly (each under 30 MB). No training library is added to the Lambda container.

Local container verification was attempted with `docker build -t medtrace-ml:local backend` but the environment's registry request to `public.ecr.aws/lambda/python:3.13` returned Forbidden. Python 3.13 native CPU tests passed; the actual Lambda base image, deployed inference latency and memory remain unverified. `packaging/results/runtime.json` records development-host peak RSS and model-load time; those measurements are not Lambda guarantees. GitHub CI must complete its container build and live checks after AWS setup.
