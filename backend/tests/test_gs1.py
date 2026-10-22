from datetime import date

import pytest

from medtrace import gs1
from tests.conftest import GS, GTIN

TODAY = date(2026, 10, 22)


def parse(raw):
    return gs1.parse(raw, today=TODAY)


def codes(issues):
    return [i.code for i in issues]


def test_check_digit_matches_gs1_example():
    assert gs1.check_digit("0950600013435") == 2
    assert gs1.has_valid_check_digit(GTIN)
    assert not gs1.has_valid_check_digit("09506000134353")


def test_ai_table_is_prefix_free():
    # Parsing relies on no AI being a prefix of another.
    for a in gs1.AI_TABLE:
        for b in gs1.AI_TABLE:
            assert a == b or not b.startswith(a), (a, b)


def test_full_pharma_datamatrix():
    result = parse(f"]d201{GTIN}17281231" f"10BATCH42{GS}21SN0001XYZ")
    assert result.valid
    assert result.symbology == "GS1 DataMatrix"
    assert (result.gtin, result.serial, result.batch) == (GTIN, "SN0001XYZ", "BATCH42")
    assert result.expiry == date(2028, 12, 31)
    out = result.to_dict()
    assert out["serialization_complete"] is True
    assert out["identifier_type"] == "trade_item"
    assert out["expired"] is False
    assert out["digital_link"] == f"https://id.gs1.org/01/{GTIN}/10/BATCH42/21/SN0001XYZ?17=281231"
    assert [e["ai"] for e in out["elements"]] == ["01", "17", "10", "21"]


@pytest.mark.parametrize("separator", ["<GS>", "{GS}", "[gs]", "\\x1d", "␝"])
def test_textual_separators_are_normalised(separator):
    result = parse(f"01{GTIN}10BATCH42{separator}21SN1")
    assert result.valid
    assert (result.batch, result.serial) == ("BATCH42", "SN1")


def test_leading_fnc1_and_trailing_newline_are_ignored():
    result = parse(f"{GS}01{GTIN}21SN1{GS}10B1\r\n")
    assert result.valid
    assert (result.serial, result.batch) == ("SN1", "B1")


def test_bracketed_human_readable_form():
    result = parse(f"(01) {GTIN} (17) 281231 (10) BATCH42 (21) SN1")
    assert result.valid
    assert result.input_format == "bracketed"
    assert (result.gtin, result.batch, result.serial) == (GTIN, "BATCH42", "SN1")


def test_sscc_logistic_unit():
    body = "03761234500000001"
    sscc = body + str(gs1.check_digit(body))
    result = parse(f"]d200{sscc}")
    assert result.valid
    assert result.identifier_type == "logistic_unit"
    assert result.sscc == sscc
    assert result.missing_serialization_elements() == []
    assert result.digital_link() == f"https://id.gs1.org/00/{sscc}"


def test_bad_check_digit_names_expected_digit():
    result = parse("0109506000134353")
    assert not result.valid
    assert codes(result.errors) == ["BAD_CHECK_DIGIT"]
    assert "expected 2" in result.errors[0].message


def test_unknown_ai_stops_parsing():
    result = parse(f"01{GTIN}9X12")
    assert codes(result.errors) == ["UNKNOWN_AI"]


def test_variable_field_over_max_length_hints_at_missing_separator():
    result = parse(f"01{GTIN}21" + "A" * 21)
    assert codes(result.errors) == ["VALUE_TOO_LONG"]
    assert "separator" in result.errors[0].message


def test_merged_fields_without_separator_trigger_warning():
    # Scanner dropped the GS: batch swallows the serial.
    result = parse(f"01{GTIN}17281231" "10BATCH4221SN1")
    assert result.valid
    assert result.batch == "BATCH4221SN1"
    assert result.missing_serialization_elements() == ["serial"]
    assert "SEPARATOR_POSSIBLY_MISSING" in codes(result.warnings)


def test_invalid_characters_rejected():
    result = parse(f"01{GTIN}21SN#1")
    assert codes(result.errors) == ["INVALID_CHARACTERS"]


def test_truncated_fixed_length_field():
    result = parse(f"01{GTIN}1728{GS}21SN1")
    assert codes(result.errors) == ["TRUNCATED"]


@pytest.mark.parametrize("raw_date, expected", [
    ("281231", date(2028, 12, 31)),
    ("280200", date(2028, 2, 29)),  # DD=00 -> last day of month (leap year)
    ("270200", date(2027, 2, 28)),
    ("761231", date(2076, 12, 31)),  # within +50 years -> this century
    ("771231", date(1977, 12, 31)),  # +51 years -> previous century
    ("991231", date(1999, 12, 31)),
])
def test_expiry_dates_and_century(raw_date, expected):
    assert parse(f"01{GTIN}17{raw_date}").expiry == expected


@pytest.mark.parametrize("raw_date", ["281301", "280230", "280032"])
def test_invalid_dates(raw_date):
    assert codes(parse(f"01{GTIN}17{raw_date}").errors) == ["INVALID_DATE"]


def test_expired_pack():
    out = parse(f"01{GTIN}17260930").to_dict()
    assert out["expired"] is True
    assert out["days_to_expiry"] == -22


def test_serial_without_gtin_is_invalid():
    assert "MISSING_GTIN" in codes(parse("21SN1").errors)


def test_conflicting_duplicate_ai():
    assert codes(parse(f"01{GTIN}21A{GS}21B").errors) == ["DUPLICATE_AI"]


def test_gtin_and_content_gtin_cannot_coexist():
    assert "INVALID_PAIR" in codes(parse(f"01{GTIN}02{GTIN}").errors)


def test_missing_elements_reported():
    out = parse(f"01{GTIN}21SN1").to_dict()
    assert out["valid"] is True
    assert out["serialization_complete"] is False
    assert out["missing_elements"] == ["batch", "expiry"]


@pytest.mark.parametrize("raw", ["", "   ", "]d2", GS * 3])
def test_empty_input(raw):
    assert codes(parse(raw).errors) == ["EMPTY"]


def test_plain_datamatrix_symbology_warns():
    result = parse(f"]d101{GTIN}")
    assert "NOT_GS1_SYMBOLOGY" in codes(result.warnings)


def test_digital_link_percent_encodes_serial():
    result = parse(f"01{GTIN}21A/B%1")
    assert result.digital_link() == f"https://id.gs1.org/01/{GTIN}/21/A%2FB%251"
