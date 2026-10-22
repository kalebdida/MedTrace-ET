"""Packaging forensics: fuse the Siamese-network result with the barcode checks.

The phone sends a photo of the pack with each scan, and the model runs here,
inside the Lambda container, not on the phone. A score computed on the device
could be forged by a tampered app; one computed server-side cannot. Running
in-process also keeps inference inside the Lambda free tier (no SageMaker
endpoint) and next to the barcode and travel evidence it is fused with.

The model is provided by the ML pipeline as an importable module, named by
the VISUAL_MODEL_MODULE environment variable, exposing:

    def load() -> verifier

where ``verifier`` has

    model_version: str
    def similarity(self, image: bytes, gtin: str) -> float | None

``similarity`` receives the raw JPEG/PNG bytes and returns how closely the
photographed packaging matches the manufacturer's reference packaging for that
GTIN, from 0 (different) to 1 (identical), or None when no reference is
enrolled for the GTIN. ``load`` runs once per container (cold start).
"""

from __future__ import annotations

import hashlib
import importlib
import logging
import math
import time
from dataclasses import dataclass
from typing import Protocol

from .flags import CRITICAL, INFO, WARNING, Flag

logger = logging.getLogger(__name__)

MATCH = "match"
INCONCLUSIVE = "inconclusive"
MISMATCH = "mismatch"
NO_REFERENCE = "no_reference"
UNAVAILABLE = "unavailable"  # no model loaded
ERROR = "error"  # model loaded but failed on this image
NOT_PERFORMED = "not_performed"  # barcode unusable, nothing to compare against


class VisualVerifier(Protocol):
    model_version: str

    def similarity(self, image: bytes, gtin: str) -> float | None: ...


@dataclass(frozen=True)
class VisualThresholds:
    mismatch_below: float = 0.5
    match_at: float = 0.8


@dataclass(frozen=True)
class VisualCheck:
    status: str
    image_sha256: str
    similarity: float | None = None
    model_version: str | None = None
    latency_ms: float | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "similarity": round(self.similarity, 4) if self.similarity is not None else None,
            "model_version": self.model_version,
            "latency_ms": self.latency_ms,
            "image_sha256": self.image_sha256,
        }


def load_verifier(module_name: str | None) -> VisualVerifier | None:
    if not module_name:
        return None
    try:
        verifier = importlib.import_module(module_name).load()
    except Exception:
        # Barcode verification must keep working even if the model cannot load.
        logger.exception("Visual model %s failed to load; packaging checks are disabled", module_name)
        return None
    logger.info("Loaded visual model %s (%s)", module_name, getattr(verifier, "model_version", "unknown"))
    return verifier


def not_performed(image: bytes) -> VisualCheck:
    return VisualCheck(NOT_PERFORMED, _sha256(image))


def check_packaging(
    verifier: VisualVerifier | None,
    image: bytes,
    gtin: str,
    thresholds: VisualThresholds,
) -> tuple[VisualCheck, list[Flag]]:
    digest = _sha256(image)
    if verifier is None:
        return VisualCheck(UNAVAILABLE, digest), [_unavailable_flag()]

    version = getattr(verifier, "model_version", None)
    started = time.perf_counter()
    try:
        score = verifier.similarity(image, gtin)
        if score is not None:
            score = float(score)
            if not (math.isfinite(score) and 0 <= score <= 1):
                raise ValueError(f"similarity {score} is outside [0, 1]")
    except Exception:
        logger.exception("Visual model %s failed on GTIN %s", version, gtin)
        return VisualCheck(ERROR, digest, model_version=version), [_unavailable_flag()]
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    if score is None:
        return VisualCheck(NO_REFERENCE, digest, None, version, latency_ms), [Flag(
            "VISUAL_NO_REFERENCE",
            INFO,
            "No reference packaging is enrolled for this product yet, so only the barcode was verified.",
        )]

    details = {
        "similarity": round(score, 4),
        "mismatch_below": thresholds.mismatch_below,
        "match_at": thresholds.match_at,
        "model_version": version,
    }
    if score < thresholds.mismatch_below:
        status, flags = MISMATCH, [Flag(
            "PACKAGING_MISMATCH",
            CRITICAL,
            "The barcode is valid but the packaging does not match the manufacturer's reference "
            "(print, colour or typography differ). A genuine serial has likely been copied onto "
            "counterfeit packaging.",
            clone_indicator=True,
            details=details,
        )]
    elif score < thresholds.match_at:
        status, flags = INCONCLUSIVE, [Flag(
            "PACKAGING_INCONCLUSIVE",
            WARNING,
            "The packaging only partly matches the manufacturer's reference. Retake the photo in "
            "good light; if it still does not match, set the pack aside.",
            details=details,
        )]
    else:
        status, flags = MATCH, []
    return VisualCheck(status, digest, score, version, latency_ms), flags


def _unavailable_flag() -> Flag:
    return Flag(
        "VISUAL_CHECK_UNAVAILABLE",
        INFO,
        "The packaging check could not run, so only the barcode was verified.",
    )


def _sha256(image: bytes) -> str:
    return hashlib.sha256(image).hexdigest()
