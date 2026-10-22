"""GS1 DataMatrix element-string parser and validator.

A pharmaceutical GS1 DataMatrix encodes a sequence of Application Identifier
(AI) elements, e.g. ``01`` GTIN, ``17`` expiry, ``10`` batch and ``21`` serial.
Fixed-length elements run straight into the next AI; variable-length elements
are terminated by the FNC1 separator, which scanners transmit as ASCII GS
(0x1D). This module turns raw scanner output, or the human-readable
``(01)...(21)...`` form, into validated, structured data.

Rules implemented from the GS1 General Specifications: the AI table below,
FNC1 separation, the mod-10 check digit, century determination for YYMMDD
dates, and "DD = 00 means the last day of the month".
"""

from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import quote

GS = "\x1d"

# AIM symbology identifiers a scanner may prepend to the decoded data.
SYMBOLOGY_IDS = {
    "]d2": "GS1 DataMatrix",
    "]Q3": "GS1 QR Code",
    "]C1": "GS1-128",
    "]e0": "GS1 DataBar",
    "]d1": "DataMatrix (non-GS1)",
}

# Textual stand-ins for GS that scanner apps and keyboard wedges emit.
_GS_ALIASES = re.compile(r"<GS>|\{GS\}|\[GS\]|\\x1d|\\u001d|␝", re.IGNORECASE)

# GS1 AI encodable character set 82.
_CSET82 = re.compile(r"[!\"%&'()*+,\-./0-9:;<=>?A-Z_a-z]+")
_DIGITS = re.compile(r"[0-9]+")
_BRACKETED_AI = re.compile(r"\((\d{2,4})\)")

DIGITAL_LINK_BASE = "https://id.gs1.org"

# The four data elements a serialised medicine pack must carry.
SERIALIZATION_ELEMENTS = {"01": "gtin", "21": "serial", "10": "batch", "17": "expiry"}


@dataclass(frozen=True)
class AIDef:
    ai: str
    key: str
    title: str
    fixed: int | None = None  # exact length, or None for variable length
    max_len: int | None = None  # upper bound for variable-length AIs
    kind: str = "alnum"  # alnum | numeric | date | datetime
    check_digit: bool = False


_AI_LIST = [
    AIDef("00", "sscc", "SSCC", fixed=18, kind="numeric", check_digit=True),
    AIDef("01", "gtin", "GTIN", fixed=14, kind="numeric", check_digit=True),
    AIDef("02", "content_gtin", "CONTENT", fixed=14, kind="numeric", check_digit=True),
    AIDef("10", "batch", "BATCH/LOT", max_len=20),
    AIDef("11", "production_date", "PROD DATE", fixed=6, kind="date"),
    AIDef("13", "packaging_date", "PACK DATE", fixed=6, kind="date"),
    AIDef("15", "best_before", "BEST BEFORE or BEST BY", fixed=6, kind="date"),
    AIDef("16", "sell_by", "SELL BY", fixed=6, kind="date"),
    AIDef("17", "expiry", "USE BY OR EXPIRY", fixed=6, kind="date"),
    AIDef("20", "variant", "VARIANT", fixed=2, kind="numeric"),
    AIDef("21", "serial", "SERIAL", max_len=20),
    AIDef("22", "cpv", "CPV", max_len=20),
    AIDef("240", "additional_id", "ADDITIONAL ID", max_len=30),
    AIDef("241", "customer_part_number", "CUST. PART No.", max_len=30),
    AIDef("30", "variable_count", "VAR. COUNT", max_len=8, kind="numeric"),
    AIDef("37", "count", "COUNT", max_len=8, kind="numeric"),
    AIDef("400", "order_number", "ORDER NUMBER", max_len=30),
    AIDef("710", "nhrn_pzn", "NHRN PZN", max_len=20),
    AIDef("711", "nhrn_cip", "NHRN CIP", max_len=20),
    AIDef("712", "nhrn_cn", "NHRN CN", max_len=20),
    AIDef("713", "nhrn_drn", "NHRN DRN", max_len=20),
    AIDef("714", "nhrn_aim", "NHRN AIM", max_len=20),
    AIDef("715", "nhrn_ndc", "NHRN NDC", max_len=20),
    AIDef("7003", "expiry_time", "EXPIRY TIME", fixed=10, kind="datetime"),
    AIDef("90", "internal_90", "INTERNAL", max_len=30),
    *(AIDef(str(n), f"internal_{n}", "INTERNAL", max_len=90) for n in range(91, 100)),
]
AI_TABLE: dict[str, AIDef] = {d.ai: d for d in _AI_LIST}

# AIs that only make sense alongside a GTIN (01) or content GTIN (02).
_NEEDS_GTIN = ("10", "11", "13", "15", "16", "17", "7003")


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    ai: str | None = None

    def to_dict(self) -> dict:
        out = {"code": self.code, "message": self.message}
        if self.ai:
            out["ai"] = self.ai
        return out


@dataclass(frozen=True)
class Element:
    definition: AIDef
    value: str
    parsed: date | datetime | None = None  # set for valid date / datetime AIs

    def to_dict(self) -> dict:
        out = {
            "ai": self.definition.ai,
            "key": self.definition.key,
            "title": self.definition.title,
            "value": self.value,
        }
        if self.parsed is not None:
            out["iso"] = self.parsed.isoformat()
        return out


@dataclass
class ParseResult:
    raw: str
    today: date
    symbology: str | None = None
    input_format: str = "element_string"
    elements: list[Element] = field(default_factory=list)
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def element(self, ai: str) -> Element | None:
        return next((e for e in self.elements if e.definition.ai == ai), None)

    def value(self, ai: str) -> str | None:
        el = self.element(ai)
        return el.value if el else None

    @property
    def gtin(self) -> str | None:
        return self.value("01")

    @property
    def serial(self) -> str | None:
        return self.value("21")

    @property
    def batch(self) -> str | None:
        return self.value("10")

    @property
    def sscc(self) -> str | None:
        return self.value("00")

    @property
    def expiry(self) -> date | None:
        el = self.element("17")
        return el.parsed if el and isinstance(el.parsed, date) else None

    @property
    def identifier_type(self) -> str | None:
        if self.sscc:
            return "logistic_unit"
        if self.gtin:
            return "trade_item"
        return None

    @property
    def days_to_expiry(self) -> int | None:
        return (self.expiry - self.today).days if self.expiry else None

    def missing_serialization_elements(self) -> list[str]:
        if self.identifier_type != "trade_item":
            return []
        return [key for ai, key in SERIALIZATION_ELEMENTS.items() if self.element(ai) is None]

    def digital_link(self) -> str | None:
        """GS1 Digital Link URI for the pack, usable as an EPCIS 2.0 identifier."""
        if not self.valid:
            return None
        if self.sscc:
            return f"{DIGITAL_LINK_BASE}/00/{self.sscc}"
        if not self.gtin:
            return None
        uri = f"{DIGITAL_LINK_BASE}/01/{self.gtin}"
        for ai in ("22", "10", "21"):
            if (v := self.value(ai)) is not None:
                uri += f"/{ai}/{quote(v, safe='')}"
        if (expiry := self.value("17")) is not None:
            uri += f"?17={expiry}"
        return uri

    def to_dict(self) -> dict:
        days = self.days_to_expiry
        missing = self.missing_serialization_elements()
        return {
            "valid": self.valid,
            "symbology": self.symbology,
            "input_format": self.input_format,
            "identifier_type": self.identifier_type,
            "gtin": self.gtin,
            "serial": self.serial,
            "batch": self.batch,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "sscc": self.sscc,
            "expired": days < 0 if days is not None else None,
            "days_to_expiry": days,
            "serialization_complete": self.identifier_type == "trade_item" and not missing,
            "missing_elements": missing,
            "digital_link": self.digital_link(),
            "elements": [e.to_dict() for e in self.elements],
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
        }


def check_digit(body: str) -> int:
    """GS1 mod-10 check digit for a numeric string (without its check digit)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def has_valid_check_digit(number: str) -> bool:
    return (
        len(number) >= 2
        and _DIGITS.fullmatch(number) is not None
        and check_digit(number[:-1]) == int(number[-1])
    )


def is_valid_text(value: str, max_len: int) -> bool:
    """True if value is 1..max_len characters from GS1 character set 82."""
    return 0 < len(value) <= max_len and _CSET82.fullmatch(value) is not None


def parse(raw: str, today: date | None = None) -> ParseResult:
    """Split a raw GS1 barcode string into validated AI elements."""
    result = ParseResult(raw=raw, today=today or date.today())
    data = raw.strip(" \t\r\n")

    for prefix, name in SYMBOLOGY_IDS.items():
        if data.startswith(prefix):
            result.symbology = name
            data = data[len(prefix):]
            break
    if result.symbology == SYMBOLOGY_IDS["]d1"]:
        result.warnings.append(Issue(
            "NOT_GS1_SYMBOLOGY",
            "Symbology identifier ]d1 marks a plain DataMatrix without FNC1, not a GS1 DataMatrix.",
        ))

    # The leading FNC1 of a GS1 symbol is sometimes transmitted as GS.
    data = _GS_ALIASES.sub(GS, data).lstrip(GS)
    if not data.strip(GS):
        result.errors.append(Issue("EMPTY", "Barcode contains no data."))
        return result

    if data.startswith("("):
        result.input_format = "bracketed"
        _split_bracketed(data, result)
    else:
        _split_element_string(data, result)

    _validate_combinations(result)
    if result.missing_serialization_elements() and GS not in data and any(
        e.definition.fixed is None for e in result.elements
    ):
        result.warnings.append(Issue(
            "SEPARATOR_POSSIBLY_MISSING",
            "No GS/FNC1 separators were received. If the scanner strips them, "
            "variable-length fields such as batch and serial merge together.",
        ))
    return result


def _match_ai(data: str, i: int) -> AIDef | None:
    # The GS1 AI table is prefix-free, so the first match is the only match.
    for length in (2, 3, 4):
        if (defn := AI_TABLE.get(data[i:i + length])) is not None:
            return defn
    return None


def _split_element_string(data: str, result: ParseResult) -> None:
    i, n = 0, len(data)
    while i < n:
        if data[i] == GS:
            i += 1
            continue
        defn = _match_ai(data, i)
        if defn is None:
            result.errors.append(Issue(
                "UNKNOWN_AI",
                f"Unrecognised or unsupported Application Identifier at position {i} "
                f"('{data[i:i + 4]}'); parsing stopped.",
            ))
            return
        start = i + len(defn.ai)
        if defn.fixed:
            end = start + defn.fixed
            if GS in data[start:end]:
                result.errors.append(Issue(
                    "TRUNCATED",
                    f"{defn.title} ({defn.ai}) needs exactly {defn.fixed} characters "
                    "but a separator interrupts it; parsing stopped.",
                    defn.ai,
                ))
                return
        else:
            sep = data.find(GS, start)
            end = n if sep == -1 else sep
        _add_element(defn, data[start:end], result)
        i = end


def _split_bracketed(data: str, result: ParseResult) -> None:
    parts = _BRACKETED_AI.split(data)
    if parts[0].strip():
        result.errors.append(Issue("UNEXPECTED_TEXT", f"Unexpected text before the first AI: '{parts[0]}'."))
    for ai, value in zip(parts[1::2], parts[2::2]):
        defn = AI_TABLE.get(ai)
        if defn is None:
            result.errors.append(Issue("UNKNOWN_AI", f"Unrecognised or unsupported Application Identifier ({ai}).", ai))
            continue
        _add_element(defn, value.strip(" " + GS), result)


def _add_element(defn: AIDef, value: str, result: ParseResult) -> None:
    label = f"{defn.title} ({defn.ai})"
    error = None
    parsed = None
    if not value:
        error = Issue("EMPTY_VALUE", f"{label} has no value.", defn.ai)
    elif defn.fixed and len(value) != defn.fixed:
        error = Issue("WRONG_LENGTH", f"{label} must be exactly {defn.fixed} characters, got {len(value)}.", defn.ai)
    elif not defn.fixed and len(value) > defn.max_len:
        error = Issue(
            "VALUE_TOO_LONG",
            f"{label} is {len(value)} characters; the maximum is {defn.max_len}. "
            "A missing GS/FNC1 separator usually causes this.",
            defn.ai,
        )
    elif defn.kind != "alnum" and not _DIGITS.fullmatch(value):
        error = Issue("NOT_NUMERIC", f"{label} must contain digits only.", defn.ai)
    elif defn.kind == "alnum" and not _CSET82.fullmatch(value):
        error = Issue("INVALID_CHARACTERS", f"{label} contains characters outside GS1 character set 82.", defn.ai)
    elif defn.check_digit and not has_valid_check_digit(value):
        error = Issue(
            "BAD_CHECK_DIGIT",
            f"{label} check digit is {value[-1]}, expected {check_digit(value[:-1])}.",
            defn.ai,
        )
    elif defn.kind == "date":
        parsed = _parse_yymmdd(value, result.today)
        if parsed is None:
            error = Issue("INVALID_DATE", f"{label} '{value}' is not a valid YYMMDD date.", defn.ai)
    elif defn.kind == "datetime":
        parsed = _parse_yymmddhhmm(value, result.today)
        if parsed is None:
            error = Issue("INVALID_DATE", f"{label} '{value}' is not a valid YYMMDDHHMM timestamp.", defn.ai)

    if error:
        result.errors.append(error)
    result.elements.append(Element(defn, value, parsed))


def _validate_combinations(result: ParseResult) -> None:
    seen: dict[str, str] = {}
    for el in result.elements:
        ai = el.definition.ai
        if ai in seen:
            if seen[ai] != el.value:
                result.errors.append(Issue("DUPLICATE_AI", f"AI ({ai}) appears twice with different values.", ai))
            else:
                result.warnings.append(Issue("DUPLICATE_AI", f"AI ({ai}) appears twice.", ai))
        seen.setdefault(ai, el.value)

    if "01" in seen and "02" in seen:
        result.errors.append(Issue("INVALID_PAIR", "GTIN (01) and CONTENT (02) cannot appear together."))
    if "21" in seen and "01" not in seen:
        result.errors.append(Issue("MISSING_GTIN", "SERIAL (21) must be accompanied by GTIN (01).", "21"))
    for ai in _NEEDS_GTIN:
        if ai in seen and "01" not in seen and "02" not in seen:
            title = AI_TABLE[ai].title
            result.errors.append(Issue("MISSING_GTIN", f"{title} ({ai}) must be accompanied by GTIN (01) or CONTENT (02).", ai))


def _resolve_century(yy: int, today: date) -> int:
    century, current_yy = divmod(today.year, 100)
    diff = yy - current_yy
    if diff >= 51:
        century -= 1
    elif diff <= -50:
        century += 1
    return century * 100 + yy


def _parse_yymmdd(value: str, today: date) -> date | None:
    yy, mm, dd = int(value[0:2]), int(value[2:4]), int(value[4:6])
    if not 1 <= mm <= 12:
        return None
    year = _resolve_century(yy, today)
    last_day = monthrange(year, mm)[1]
    if dd == 0:
        dd = last_day
    if dd > last_day:
        return None
    return date(year, mm, dd)


def _parse_yymmddhhmm(value: str, today: date) -> datetime | None:
    day = _parse_yymmdd(value[:6], today)
    hh, mi = int(value[6:8]), int(value[8:10])
    if day is None or value[4:6] == "00" or hh > 23 or mi > 59:
        return None
    return datetime(day.year, day.month, day.day, hh, mi)
