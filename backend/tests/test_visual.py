import base64
import hashlib
import json

import pytest

import app
from medtrace import visual
from medtrace.config import Settings
from tests.conftest import ADAMA, DESSIE, GTIN, ago, call, claims_for, http_event, iso, pharma_barcode
from tests.fake_visual_model import FakeVerifier, photo

THRESHOLDS = visual.VisualThresholds(mismatch_below=0.5, match_at=0.8)


@pytest.fixture
def model(aws, monkeypatch):
    """Load the test-double model the same way production loads Person 2's module."""
    monkeypatch.setenv("VISUAL_MODEL_MODULE", "tests.fake_visual_model")
    monkeypatch.setattr(app, "_services", None)
    return aws


def scan_with_photo(image, barcode=None, location=ADAMA, minutes_ago=0, site_id="PH-ADAMA-001"):
    body = {
        "barcode": barcode or pharma_barcode(),
        "location": location,
        "scanned_at": iso(ago(minutes=minutes_ago)),
        "package_image": base64.b64encode(image).decode() if isinstance(image, bytes) else image,
    }
    return call(http_event("POST", "/scan", body, claims=claims_for(site_id=site_id)))


def codes(body):
    return [f["code"] for f in body["flags"]]


# --- Fusion rules (unit) -----------------------------------------------------

@pytest.mark.parametrize("instruction, status, flag_codes", [
    ("score=0.93", visual.MATCH, []),
    ("score=0.80", visual.MATCH, []),
    ("score=0.65", visual.INCONCLUSIVE, ["PACKAGING_INCONCLUSIVE"]),
    ("score=0.49", visual.MISMATCH, ["PACKAGING_MISMATCH"]),
    ("no-reference", visual.NO_REFERENCE, ["VISUAL_NO_REFERENCE"]),
    ("crash", visual.ERROR, ["VISUAL_CHECK_UNAVAILABLE"]),
    ("score=1.7", visual.ERROR, ["VISUAL_CHECK_UNAVAILABLE"]),
    ("score=nan", visual.ERROR, ["VISUAL_CHECK_UNAVAILABLE"]),
])
def test_score_to_status_and_flags(instruction, status, flag_codes):
    image = photo(instruction)
    check, flags = visual.check_packaging(FakeVerifier(), image, GTIN, THRESHOLDS)
    assert check.status == status
    assert [f.code for f in flags] == flag_codes
    assert check.image_sha256 == hashlib.sha256(image).hexdigest()


def test_mismatch_is_a_clone_indicator():
    _, [flag] = visual.check_packaging(FakeVerifier(), photo("score=0.2"), GTIN, THRESHOLDS)
    assert flag.severity == "critical"
    assert flag.clone_indicator
    assert flag.details["similarity"] == 0.2
    assert flag.details["model_version"] == "fake-siamese-1"


def test_no_model_loaded_is_reported_not_faked():
    check, [flag] = visual.check_packaging(None, photo("score=0.9"), GTIN, THRESHOLDS)
    assert check.status == visual.UNAVAILABLE
    assert check.similarity is None
    assert flag.code == "VISUAL_CHECK_UNAVAILABLE"


def test_broken_model_module_does_not_break_loading():
    assert visual.load_verifier("tests.broken_visual_model") is None
    assert visual.load_verifier("tests.module_that_does_not_exist") is None
    assert visual.load_verifier(None) is None


def test_threshold_settings_validated():
    settings = Settings.from_env({"VISUAL_MISMATCH_BELOW": "0.4", "VISUAL_MATCH_AT": "0.9"})
    assert (settings.visual_mismatch_below, settings.visual_match_at) == (0.4, 0.9)
    with pytest.raises(ValueError, match="Visual thresholds"):
        Settings.from_env({"VISUAL_MISMATCH_BELOW": "0.9", "VISUAL_MATCH_AT": "0.4"})
    with pytest.raises(ValueError, match="Visual thresholds"):
        Settings.from_env({"VISUAL_MATCH_AT": "1.5"})


# --- /scan integration -------------------------------------------------------

def test_genuine_packaging_passes(model):
    status, body = scan_with_photo(photo("score=0.91"))
    assert status == 200
    assert body["verdict"] == "PASS"
    assert body["visual"]["status"] == "match"
    assert body["visual"]["similarity"] == 0.91
    item = model["table"].scan()["Items"][0]
    assert item["visual"]["image_sha256"] == hashlib.sha256(photo("score=0.91")).hexdigest()


def test_cloned_code_on_fake_packaging_is_caught_on_first_scan(model):
    # No travel history yet: only the packaging gives the counterfeit away.
    _, body = scan_with_photo(photo("score=0.12"))
    assert body["verdict"] == "FAIL"
    assert body["clone_suspected"] is True
    assert codes(body) == ["PACKAGING_MISMATCH"]
    assert body["alert_sent"] is True
    [envelope] = model["alerts"]()
    alert = json.loads(envelope["Message"])
    assert alert["flags"][0]["code"] == "PACKAGING_MISMATCH"
    assert alert["visual"]["status"] == "mismatch"
    assert alert["site_source"] == "token"


def test_packaging_and_travel_evidence_combine(model):
    scan_with_photo(photo("score=0.95"), location=ADAMA, minutes_ago=40)
    _, body = scan_with_photo(photo("score=0.3"), location=DESSIE, site_id="PH-DESSIE-007")
    assert codes(body) == ["PACKAGING_MISMATCH", "IMPOSSIBLE_TRAVEL"]


def test_blurry_photo_only_warns(model):
    _, body = scan_with_photo(photo("score=0.7"))
    assert body["verdict"] == "WARN"
    assert codes(body) == ["PACKAGING_INCONCLUSIVE"]
    assert body["clone_suspected"] is False


def test_model_crash_keeps_barcode_verdict(model, capsys):
    status, body = scan_with_photo(photo("crash"))
    assert status == 200
    assert body["verdict"] == "PASS"
    assert codes(body) == ["VISUAL_CHECK_UNAVAILABLE"]
    emf = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert emf["VisualCheckErrors"] == 1


def test_photo_without_model_configured(aws):
    _, body = scan_with_photo(photo("score=0.9"))
    assert body["visual"]["status"] == "unavailable"
    assert codes(body) == ["VISUAL_CHECK_UNAVAILABLE"]


def test_model_not_run_when_barcode_is_invalid(model):
    _, body = scan_with_photo(photo("score=0.1"), barcode="0109506000134353")
    assert body["visual"]["status"] == "not_performed"
    assert codes(body) == ["INVALID_BARCODE"]
    assert app.get_services().visual.calls == []


def test_model_receives_the_gtin(model):
    scan_with_photo(photo("score=0.9"))
    assert app.get_services().visual.calls == [GTIN]


def test_scan_without_photo_has_no_visual_section(model):
    status, body = call(http_event("POST", "/scan", {"barcode": pharma_barcode()}, claims=claims_for()))
    assert status == 200
    assert body["visual"] is None


def test_data_url_photo_accepted(model):
    data_url = "data:image/jpeg;base64," + base64.b64encode(photo("score=0.9")).decode()
    _, body = scan_with_photo(data_url)
    assert body["visual"]["status"] == "match"


def test_health_reports_loaded_model(model):
    assert call(http_event("GET", "/health"))[1]["visual_model_loaded"] is True


@pytest.mark.parametrize("image, status, message", [
    ("not base64!!", 400, "not valid base64"),
    (base64.b64encode(b"GIF89a....").decode(), 400, "JPEG or PNG"),
    (base64.b64encode(b"\xff\xd8\xff" + b"0" * 1_500_000).decode(), 413, "exceeds"),
    (12345, 400, "base64-encoded"),
])
def test_bad_photos_rejected(model, image, status, message):
    code, body = scan_with_photo(image)
    assert code == status
    assert message in body["error"]
