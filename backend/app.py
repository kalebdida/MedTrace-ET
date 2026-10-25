"""MedTrace-ET backend Lambda handler.

Routes (API Gateway REST or HTTP API, Lambda proxy integration):

    GET  /health    liveness probe
    POST /parse     parse and validate a raw GS1 barcode (stateless)
    POST /scan      verify a scanned pack: parse it, run the clone,
                    travel-velocity and packaging checks, append the scan to
                    the audit log and raise an SNS alert on a clone
    GET  /history   audit trail of one pack (?gtin=&serial= or ?sscc=),
                    with hash-chain verification
    GET  /alerts    inspectors only: newest clone alerts across all packs
                    (?limit=&before=), Postgres audit log only

/scan and /history require a caller authenticated by the API Gateway JWT
(Cognito) authorizer unless REQUIRE_AUTH=false; /parse and /health are public.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import re
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

import boto3

from medtrace import gs1, metrics, visual
from medtrace.alerts import AlertPublisher
from medtrace.audit import AuditLog, ChainConflict, verify_chain
from medtrace.config import Settings
from medtrace.flags import CRITICAL, INFO, WARNING, Flag, verdict
from medtrace.jsonutil import json_default
from medtrace.velocity import GeoPoint, ScanObservation, VelocityConfig, assess_clone_risk

logger = logging.getLogger("medtrace")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

EAT = timezone(timedelta(hours=3), "EAT")  # Ethiopia; no daylight saving
EVENT_TYPES = {  # request event_type -> EPCIS business step (CBV)
    "verify": "inspecting",
    "receive": "receiving",
    "ship": "shipping",
    "dispense": "dispensing",
}
MAX_IMAGE_BYTES = 1_500_000
MAX_BODY_BYTES = 2_200_000  # room for one base64-encoded package photo
_IMAGE_SIGNATURES = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")  # JPEG, PNG
MAX_BARCODE_CHARS = 512
MAX_CLOCK_SKEW = timedelta(minutes=5)
APPEND_ATTEMPTS = 3
UNIDENTIFIED = "UNIDENTIFIED#"
_ID_PATTERN = re.compile(r"[A-Za-z0-9._:@/-]{1,64}")


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Services:
    settings: Settings
    audit: AuditLog | None
    alerts: AlertPublisher | None
    visual: visual.VisualVerifier | None


_services: Services | None = None


def get_services() -> Services:
    """Build AWS clients once per container and reuse them across invocations."""
    global _services
    if _services is None:
        settings = Settings.from_env()
        audit = AuditLog(boto3.resource("dynamodb").Table(settings.table_name)) if settings.table_name and not os.environ.get("DATABASE_URL") else None
        alerts = AlertPublisher(boto3.client("sns"), settings.alert_topic_arn) if settings.alert_topic_arn else None
        if os.environ.get("DATABASE_URL"):
            from medtrace.audit_postgres import AuditLog as PostgresAuditLog
            audit = PostgresAuditLog(os.environ["DATABASE_URL"])
        if not settings.alert_topic_arn and (os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("NTFY_TOPIC_URL")):
            from medtrace.alerts_webhook import AlertPublisher as WebhookPublisher
            alerts = WebhookPublisher(os.environ.get("DISCORD_WEBHOOK_URL"), os.environ.get("NTFY_TOPIC_URL"))
        verifier = visual.load_verifier(settings.visual_model_module)
        _services = Services(settings, audit, alerts, verifier)
    return _services


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None)
    origin = "*"
    try:
        services = get_services()
        origin = services.settings.cors_allow_origin
        method, path = _route(event)
        if method == "OPTIONS":
            return _response(204, None, origin)
        handler = ROUTES.get((method, path))
        if handler is None:
            if any(route_path == path for _, route_path in ROUTES):
                raise HttpError(405, f"{method} is not allowed on {path}")
            raise HttpError(404, f"No route for {method} {path}")
        return _response(200, handler(event, services), origin)
    except HttpError as err:
        return _response(err.status, {"error": err.message}, origin)
    except Exception:
        logger.exception("Unhandled error (request %s)", request_id)
        return _response(500, {"error": "Internal server error", "request_id": request_id}, origin)


# --- Route handlers ---------------------------------------------------------

def handle_health(event, services: Services) -> dict:
    return {
        "status": "ok",
        "audit_log_configured": services.audit is not None,
        "alerts_configured": services.alerts is not None,
        "auth_required": services.settings.require_auth,
        "visual_model_loaded": services.visual is not None,
    }


def handle_parse(event, services: Services) -> dict:
    barcode = _barcode(_json_body(event))
    return gs1.parse(barcode, today=_now().astimezone(EAT).date()).to_dict()


def handle_scan(event, services: Services) -> dict:
    if services.audit is None:
        raise HttpError(503, "Scan logging is not configured (SCAN_TABLE_NAME is unset)")
    started = time.perf_counter()
    settings = services.settings
    caller = _require_caller(event, settings)
    req = _bind_site(_scan_request(_json_body(event)), caller)
    received_at = _now()

    pre_flags: list[Flag] = []
    scanned_at = req.scanned_at or received_at
    if scanned_at - received_at > MAX_CLOCK_SKEW:
        pre_flags.append(Flag(
            "CLOCK_SKEW",
            INFO,
            "The device clock is ahead of the server; server time was used for this scan.",
            details={"device_scanned_at": scanned_at.isoformat()},
        ))
        scanned_at = received_at

    parsed = gs1.parse(req.barcode, today=received_at.astimezone(EAT).date())
    pre_flags.extend(_barcode_flags(parsed, settings))
    packaging = None
    if req.package_image is not None:
        if parsed.valid and parsed.gtin:
            thresholds = visual.VisualThresholds(settings.visual_mismatch_below, settings.visual_match_at)
            packaging, visual_flags = visual.check_packaging(services.visual, req.package_image, parsed.gtin, thresholds)
            pre_flags.extend(visual_flags)
        else:
            packaging = visual.not_performed(req.package_image)
    pk = _identity_key(parsed, received_at)
    tracked = not pk.startswith(UNIDENTIFIED)
    current = ScanObservation(
        event_id=str(uuid.uuid4()),
        scanned_at=scanned_at,
        event_type=req.event_type,
        site_id=req.site_id,
        location=req.location,
    )
    velocity_config = VelocityConfig(settings.max_speed_kmh, settings.min_distance_km)

    # Read history, assess, append. If another scan of the same pack is
    # appended in between, re-read so the assessment includes it.
    for attempt in range(1, APPEND_ATTEMPTS + 1):
        history = services.audit.recent(pk, settings.history_limit if tracked else 1)
        assessment = (
            assess_clone_risk(current, [_observation(r) for r in history], velocity_config)
            if tracked else None
        )
        flags = pre_flags + (assessment.flags if assessment else [])
        fields = _audit_fields(req, current, received_at, parsed, flags, assessment, packaging)
        try:
            stored = services.audit.append(pk, history[0] if history else None, fields)
            break
        except ChainConflict:
            if attempt == APPEND_ATTEMPTS:
                raise
            logger.info("Concurrent scan of %s; re-reading history (attempt %d)", pk, attempt)

    clone = stored["clone_suspected"]
    alert_sent = False
    if clone and services.alerts:
        alert_sent = services.alerts.publish_clone_alert(stored, flags)
    elif clone:
        logger.warning("Clone suspected for %s but ALERT_TOPIC_ARN is not configured", pk)

    location = req.location
    metrics.emit(
        settings.metrics_namespace,
        [
            ("ScansProcessed", 1, metrics.COUNT),
            ("CloneAlerts", int(clone), metrics.COUNT),
            ("AlertFailures", int(clone and services.alerts is not None and not alert_sent), metrics.COUNT),
            ("InvalidBarcodes", int(not parsed.valid), metrics.COUNT),
            ("VisualMismatches", int(packaging is not None and packaging.status == visual.MISMATCH), metrics.COUNT),
            ("VisualCheckErrors", int(packaging is not None and packaging.status == visual.ERROR), metrics.COUNT),
            ("ScanLatency", round((time.perf_counter() - started) * 1000, 1), metrics.MILLISECONDS),
        ],
        {"Service": "MedTraceBackend"},
        {
            "event_id": current.event_id,
            "verdict": stored["verdict"],
            "flag_codes": [f.code for f in flags],
            "event_type": req.event_type,
            "site_id": req.site_id,
            "site_source": req.site_source,
            "actor": req.actor,
            "visual_status": packaging.status if packaging else None,
            "visual_similarity": packaging.similarity if packaging else None,
            "lat": location.lat if location else None,
            "lon": location.lon if location else None,
            "gtin": parsed.gtin,
            "pk": pk,
            "seq": stored["seq"],
            # A copy of each hash outside DynamoDB lets auditors detect
            # tampering even if someone with table access rewrote a chain.
            "record_hash": stored["record_hash"],
            "alert_sent": alert_sent,
        },
    )

    return {
        "event_id": current.event_id,
        "verdict": stored["verdict"],
        "clone_suspected": clone,
        "flags": [f.to_dict() for f in flags],
        "site_id": req.site_id,
        "product": parsed.to_dict(),
        "visual": packaging.to_dict() if packaging else None,
        "travel": {
            "legs": [leg.to_dict() for leg in sorted(assessment.legs, key=lambda leg: leg.speed_kmh, reverse=True)[:5]],
            "features": assessment.features,
        } if assessment else None,
        "audit": {
            "pk": pk,
            "seq": stored["seq"],
            "prev_hash": stored["prev_hash"],
            "record_hash": stored["record_hash"],
        },
        "alert_sent": alert_sent,
    }


def handle_history(event, services: Services) -> dict:
    if services.audit is None:
        raise HttpError(503, "Scan logging is not configured (SCAN_TABLE_NAME is unset)")
    _require_caller(event, services.settings)
    params = event.get("queryStringParameters") or {}
    sscc, gtin, serial = params.get("sscc"), params.get("gtin"), params.get("serial")
    if sscc:
        if len(sscc) != 18 or not gs1.has_valid_check_digit(sscc):
            raise HttpError(400, "sscc must be 18 digits with a valid check digit")
        pk = f"SSCC#{sscc}"
    elif gtin and serial:
        if len(gtin) != 14 or not gs1.has_valid_check_digit(gtin):
            raise HttpError(400, "gtin must be 14 digits with a valid check digit")
        if not gs1.is_valid_text(serial, 20):
            raise HttpError(400, "serial must be 1-20 characters from the GS1 character set")
        pk = f"SGTIN#{gtin}#{serial}"
    else:
        raise HttpError(400, "Provide either sscc, or both gtin and serial")

    items, truncated = services.audit.full_history(pk)
    if not items:
        raise HttpError(404, "No scans recorded for this pack")
    return {
        "identity": pk,
        "scan_count": len(items),
        "truncated": truncated,
        "chain": verify_chain(items),
        "events": items,
    }


ALERTS_DEFAULT_LIMIT = 20
ALERTS_MAX_LIMIT = 100


def handle_alerts(event, services: Services) -> dict:
    if services.audit is None:
        raise HttpError(503, "Scan logging is not configured (SCAN_TABLE_NAME is unset)")
    caller = _caller(event, services.settings)
    if caller is None:
        raise HttpError(401, "Sign-in required")
    if not caller.inspector:
        raise HttpError(403, "Only inspector accounts can list alerts")
    if not hasattr(services.audit, "recent_alerts"):
        raise HttpError(501, "Listing alerts needs the Postgres audit log; look packs up with /history instead")

    params = event.get("queryStringParameters") or {}
    raw_limit = params.get("limit") or str(ALERTS_DEFAULT_LIMIT)
    if not raw_limit.isdigit() or not 1 <= int(raw_limit) <= ALERTS_MAX_LIMIT:
        raise HttpError(400, f"limit must be between 1 and {ALERTS_MAX_LIMIT}")
    before = params.get("before")
    if before is not None:
        try:
            before = _timestamp(before).isoformat()
        except HttpError:
            raise HttpError(400, "before must be an ISO-8601 timestamp with a timezone offset") from None

    records, next_before = services.audit.recent_alerts(int(raw_limit), before)
    return {"alerts": [_alert_summary(r) for r in records], "next_before": next_before}


def _alert_summary(record: dict) -> dict:
    keep = (
        "event_id", "received_at", "scanned_at", "event_type", "site_id", "site_source", "actor",
        "location", "gtin", "serial", "batch", "expiry", "sscc", "verdict", "pk", "seq", "record_hash",
    )
    summary = {k: record[k] for k in keep if k in record}
    summary["flags"] = [
        {k: f.get(k) for k in ("code", "severity", "message")}
        for f in record.get("flags", [])
        if f.get("clone_indicator")
    ]
    if record.get("visual"):
        summary["visual_status"] = record["visual"].get("status")
    return summary


ROUTES = {
    ("GET", "/health"): handle_health,
    ("POST", "/parse"): handle_parse,
    ("POST", "/scan"): handle_scan,
    ("GET", "/history"): handle_history,
    ("GET", "/alerts"): handle_alerts,
}


# --- Scan helpers -----------------------------------------------------------

def _barcode_flags(parsed: gs1.ParseResult, settings: Settings) -> list[Flag]:
    if not parsed.valid:
        return [Flag(
            "INVALID_BARCODE",
            CRITICAL,
            "The barcode is not a valid GS1 code. " + " ".join(e.message for e in parsed.errors[:3]),
            details={"errors": [e.code for e in parsed.errors]},
        )]

    flags = []
    if parsed.identifier_type is None:
        flags.append(Flag(
            "NO_PRODUCT_IDENTIFIER",
            WARNING,
            "The barcode carries neither a GTIN nor an SSCC, so the pack cannot be traced.",
        ))
    missing = parsed.missing_serialization_elements()
    if missing:
        message = f"The barcode is missing: {', '.join(missing)}."
        if "serial" in missing:
            message += " Without a serial number the pack cannot be checked for cloning."
        flags.append(Flag("INCOMPLETE_SERIALIZATION", WARNING, message, details={"missing": missing}))

    days = parsed.days_to_expiry
    if days is not None and days < 0:
        flags.append(Flag("EXPIRED", CRITICAL, f"Expired on {parsed.expiry.isoformat()}. Do not dispense."))
    elif days is not None and days <= settings.near_expiry_days:
        flags.append(Flag("NEAR_EXPIRY", WARNING, f"Expires in {days} days ({parsed.expiry.isoformat()})."))
    return flags


def _identity_key(parsed: gs1.ParseResult, received_at: datetime) -> str:
    if parsed.valid and parsed.sscc:
        return f"SSCC#{parsed.sscc}"
    if parsed.valid and parsed.gtin and parsed.serial:
        return f"SGTIN#{parsed.gtin}#{parsed.serial}"
    # Untraceable scans are still logged, grouped by day, for EFDA review.
    return f"{UNIDENTIFIED}{received_at:%Y-%m-%d}"


def _audit_fields(
    req: ScanRequest,
    current: ScanObservation,
    received_at: datetime,
    parsed: gs1.ParseResult,
    flags: list[Flag],
    assessment,
    packaging: visual.VisualCheck | None,
) -> dict:
    fields = {
        "record_type": "SCAN",
        "schema_version": 1,
        "event_id": current.event_id,
        "received_at": received_at.isoformat(),
        "scanned_at": current.scanned_at.isoformat(),
        "event_type": req.event_type,
        "biz_step": EVENT_TYPES[req.event_type],
        "site_id": req.site_id,
        "site_source": req.site_source,
        "actor": req.actor,
        "device_id": req.device_id,
        "location": _location_dict(req.location),
        "barcode_raw": req.barcode,
        "barcode_valid": parsed.valid,
        "gtin": parsed.gtin,
        "serial": parsed.serial,
        "batch": parsed.batch,
        "expiry": parsed.expiry.isoformat() if parsed.expiry else None,
        "sscc": parsed.sscc,
        "verdict": verdict(flags),
        "clone_suspected": any(f.clone_indicator for f in flags),
        "flags": [f.to_dict() for f in flags],
        "travel_features": assessment.features if assessment else None,
        "visual": packaging.to_dict() if packaging else None,
    }
    return {k: v for k, v in fields.items() if v is not None}


def _observation(record: dict) -> ScanObservation:
    loc = record.get("location")
    return ScanObservation(
        event_id=record["event_id"],
        scanned_at=datetime.fromisoformat(record["scanned_at"]),
        event_type=record.get("event_type", "verify"),
        site_id=record.get("site_id"),
        location=GeoPoint(
            float(loc["lat"]),
            float(loc["lon"]),
            float(loc["accuracy_m"]) if loc.get("accuracy_m") is not None else None,
        ) if loc else None,
    )


def _location_dict(location: GeoPoint | None) -> dict | None:
    if location is None:
        return None
    out = {"lat": location.lat, "lon": location.lon}
    if location.accuracy_m is not None:
        out["accuracy_m"] = location.accuracy_m
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Request parsing ----------------------------------------------------------

@dataclass(frozen=True)
class ScanRequest:
    barcode: str
    event_type: str
    location: GeoPoint | None
    site_id: str | None
    device_id: str | None
    scanned_at: datetime | None  # None: use server receive time
    package_image: bytes | None = None
    site_source: str | None = None  # "token" (from sign-in) or "client" (from request body)
    actor: str | None = None  # authenticated user (JWT sub)


def _scan_request(body: dict) -> ScanRequest:
    event_type = body.get("event_type", "verify")
    if event_type not in EVENT_TYPES:
        raise HttpError(400, f"event_type must be one of: {', '.join(EVENT_TYPES)}")
    return ScanRequest(
        barcode=_barcode(body),
        event_type=event_type,
        location=_location(body.get("location")),
        site_id=_optional_id(body, "site_id"),
        device_id=_optional_id(body, "device_id"),
        scanned_at=_timestamp(body.get("scanned_at")),
        package_image=_package_image(body.get("package_image")),
    )


def _barcode(body: dict) -> str:
    raw = body.get("barcode")
    if not isinstance(raw, str) or not raw.strip():
        raise HttpError(400, "barcode is required: the raw text decoded from the GS1 DataMatrix")
    if len(raw) > MAX_BARCODE_CHARS:
        raise HttpError(400, f"barcode must be at most {MAX_BARCODE_CHARS} characters")
    return raw


def _package_image(value) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HttpError(400, "package_image must be a base64-encoded JPEG or PNG")
    if value.startswith("data:"):  # tolerate data URLs from web/mobile clients
        value = value.partition(",")[2]
    try:
        image = base64.b64decode(value, validate=True)
    except ValueError:
        raise HttpError(400, "package_image is not valid base64") from None
    if len(image) > MAX_IMAGE_BYTES:
        raise HttpError(413, f"package_image exceeds {MAX_IMAGE_BYTES} bytes")
    if not image.startswith(_IMAGE_SIGNATURES):
        raise HttpError(400, "package_image must be a JPEG or PNG")
    return image


def _location(value) -> GeoPoint | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise HttpError(400, "location must be an object with lat and lon")
    lat, lon, accuracy = value.get("lat"), value.get("lon"), value.get("accuracy_m")
    if not _is_number(lat) or not -90 <= lat <= 90:
        raise HttpError(400, "location.lat must be a number between -90 and 90")
    if not _is_number(lon) or not -180 <= lon <= 180:
        raise HttpError(400, "location.lon must be a number between -180 and 180")
    if accuracy is not None and (not _is_number(accuracy) or accuracy < 0):
        raise HttpError(400, "location.accuracy_m must be a non-negative number of metres")
    return GeoPoint(float(lat), float(lon), float(accuracy) if accuracy is not None else None)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _optional_id(body: dict, name: str) -> str | None:
    value = body.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise HttpError(400, f"{name} must be 1-64 characters: letters, digits or ._:@/-")
    return value


def _timestamp(value) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HttpError(400, "scanned_at must be an ISO-8601 string")
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        raise HttpError(400, "scanned_at must be an ISO-8601 timestamp") from None
    if ts.tzinfo is None:
        raise HttpError(400, "scanned_at must include a timezone offset, e.g. 2026-10-22T09:15:00+03:00")
    return ts.astimezone(timezone.utc)


# --- Authentication -----------------------------------------------------------

@dataclass(frozen=True)
class Caller:
    subject: str
    site_id: str | None
    inspector: bool = False


INSPECTOR_ROLE = "inspector"
INSPECTOR_GROUP = "inspectors"  # Cognito group on the AWS path


def _is_inspector(claims: dict) -> bool:
    if claims.get("custom:role") == INSPECTOR_ROLE:
        return True
    groups = claims.get("cognito:groups") or []
    if isinstance(groups, str):  # API Gateway passes lists as "[a b]" or "a,b"
        groups = groups.strip("[]").replace(",", " ").split()
    return INSPECTOR_GROUP in groups


def _caller(event: dict, settings: Settings) -> Caller | None:
    """Claims verified by the API Gateway authorizer; clients cannot set requestContext."""
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    # HTTP API JWT authorizer: authorizer.jwt.claims; REST API Cognito authorizer: authorizer.claims
    claims = (authorizer.get("jwt") or {}).get("claims") or authorizer.get("claims")
    if not isinstance(claims, dict) or not claims.get("sub"):
        return None
    site_id = claims.get(settings.site_claim) or None
    if site_id is not None and not (isinstance(site_id, str) and _ID_PATTERN.fullmatch(site_id)):
        raise HttpError(403, "The account's site_id claim is malformed")
    return Caller(str(claims["sub"]), site_id, _is_inspector(claims))


def _require_caller(event: dict, settings: Settings) -> Caller | None:
    caller = _caller(event, settings)
    if caller is None and settings.require_auth:
        raise HttpError(401, "Sign-in required")
    return caller


def _bind_site(req: ScanRequest, caller: Caller | None) -> ScanRequest:
    """The signed-in account's site wins; a request body may only repeat it."""
    actor = caller.subject if caller else None
    if caller and caller.site_id:
        if req.site_id and req.site_id != caller.site_id:
            raise HttpError(403, f"site_id {req.site_id} does not match the signed-in account's site")
        return replace(req, site_id=caller.site_id, site_source="token", actor=actor)
    return replace(req, site_source="client" if req.site_id else None, actor=actor)


# --- HTTP plumbing ------------------------------------------------------------

def _route(event: dict) -> tuple[str, str]:
    context = event.get("requestContext") or {}
    http = context.get("http")
    if http:  # HTTP API, payload format 2.0
        method = http.get("method", "")
        path = event.get("rawPath") or http.get("path") or "/"
        stage = context.get("stage")
        if stage and stage != "$default" and path.startswith(f"/{stage}/"):
            path = path[len(stage) + 1:]
    else:  # REST API, payload format 1.0
        method = event.get("httpMethod", "")
        path = event.get("path") or "/"
    return method.upper(), path.rstrip("/") or "/"


def _json_body(event: dict) -> dict:
    body = event.get("body")
    if body is None:
        raise HttpError(400, "A JSON request body is required")
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise HttpError(400, "Request body is not valid base64-encoded UTF-8") from None
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise HttpError(413, f"Request body exceeds {MAX_BODY_BYTES} bytes")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HttpError(400, "Request body must be valid JSON") from None
    if not isinstance(payload, dict):
        raise HttpError(400, "Request body must be a JSON object")
    return payload


def _response(status: int, body, origin: str) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Api-Key",
        },
        "body": "" if body is None else json.dumps(body, default=json_default),
    }
