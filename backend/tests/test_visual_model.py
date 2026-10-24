"""Real ONNX smoke/regression checks; statistical evaluation lives under ml/."""

import base64
import json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
import visual_model
from medtrace.visual import VisualThresholds, check_packaging
from tests.conftest import call, http_event, pharma_barcode, claims_for

FIXTURES = Path(__file__).parent / "fixtures/packaging"
THRESHOLDS = json.loads(
    (Path(visual_model.__file__).parent / "thresholds.json").read_text()
)


@pytest.fixture(scope="module")
def verifier():
    return visual_model.load()


def test_real_model_scores_and_unknown_reference(verifier):
    assert (
        verifier.similarity((FIXTURES / "genuine.jpg").read_bytes(), "09506000134352")
        >= THRESHOLDS["VISUAL_MATCH_AT"]
    )
    assert (
        verifier.similarity(
            (FIXTURES / "counterfeit.png").read_bytes(), "09506000134352"
        )
        < THRESHOLDS["VISUAL_MISMATCH_BELOW"]
    )
    assert verifier.similarity(b"not decoded for an unknown GTIN", "unknown") is None


def test_bad_image_is_reported_without_breaking_scanning(verifier):
    check, flags = check_packaging(
        verifier, b"corrupt", "09506000134352", VisualThresholds()
    )
    assert check.status == "error"
    assert flags[0].code == "VISUAL_CHECK_UNAVAILABLE"


def test_exif_orientation_and_normalization():
    image = Image.new("RGB", (30, 20), "red")
    image.paste("blue", (0, 0, 15, 20))
    image.getexif()[274] = 6
    # Remove orientation from the manually rotated expected image.
    manual = image.transpose(Image.Transpose.ROTATE_270)
    manual.getexif()[274] = 1
    np.testing.assert_array_equal(
        visual_model.preprocess(image), visual_model.preprocess(manual)
    )
    assert visual_model.preprocess(image).shape == (1, 3, 224, 224)


def test_real_model_in_scan_flow(aws, monkeypatch):
    monkeypatch.setenv("VISUAL_MODEL_MODULE", "visual_model")
    for key, value in THRESHOLDS.items():
        monkeypatch.setenv(key, str(value))
    event = http_event(
        "POST",
        "/scan",
        dict(
            barcode=pharma_barcode(),
            package_image=base64.b64encode(
                (FIXTURES / "counterfeit.png").read_bytes()
            ).decode(),
        ),
        claims=claims_for(site_id="PH-ADAMA-001"),
    )
    status, body = call(event)
    assert status == 200
    assert body["visual"]["status"] == "mismatch"
    assert body["clone_suspected"] is True
    assert body["alert_sent"] is True
    assert aws["alerts"]()
