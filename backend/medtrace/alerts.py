"""Amazon SNS alerts for intercepted cloned barcodes."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from botocore.exceptions import BotoCoreError, ClientError

from .flags import Flag
from .jsonutil import json_default

logger = logging.getLogger(__name__)

SUBJECT = "MedTrace-ET ALERT: cloned barcode intercepted"


class AlertPublisher:
    def __init__(self, sns_client, topic_arn: str):
        self._sns = sns_client
        self._topic_arn = topic_arn

    def publish_clone_alert(self, record: Mapping, flags: list[Flag]) -> bool:
        """Publish the alert; returns False instead of raising so the scan result is never lost."""
        payload = {
            "alert_type": "CLONED_BARCODE",
            "event_id": record.get("event_id"),
            "gtin": record.get("gtin"),
            "serial": record.get("serial"),
            "batch": record.get("batch"),
            "expiry": record.get("expiry"),
            "sscc": record.get("sscc"),
            "event_type": record.get("event_type"),
            "scanned_at": record.get("scanned_at"),
            "site_id": record.get("site_id"),
            "site_source": record.get("site_source"),
            "actor": record.get("actor"),
            "device_id": record.get("device_id"),
            "location": record.get("location"),
            "flags": [f.to_dict() for f in flags if f.clone_indicator],
            "audit": {"pk": record["pk"], "seq": record["seq"], "record_hash": record["record_hash"]},
        }
        try:
            self._sns.publish(
                TopicArn=self._topic_arn,
                Subject=SUBJECT,
                MessageStructure="json",
                Message=json.dumps({
                    "default": json.dumps(payload, default=json_default),
                    "email": _email_body(payload),
                }),
                MessageAttributes={
                    "alert_type": {"DataType": "String", "StringValue": "CLONED_BARCODE"},
                    "severity": {"DataType": "String", "StringValue": "critical"},
                },
            )
        except (BotoCoreError, ClientError):
            logger.exception("Failed to publish clone alert for %s", record.get("pk"))
            return False
        return True


def _email_body(p: Mapping) -> str:
    loc = p.get("location") or {}
    where = f"({loc['lat']}, {loc['lon']})" if "lat" in loc else "location not reported"
    site_note = " (verified by sign-in)" if p.get("site_source") == "token" else ""
    lines = [
        "CLONED BARCODE INTERCEPTED",
        "",
        f"GTIN:    {p.get('gtin') or '-'}",
        f"Serial:  {p.get('serial') or '-'}",
        f"SSCC:    {p.get('sscc') or '-'}",
        f"Batch:   {p.get('batch') or '-'}    Expiry: {p.get('expiry') or '-'}",
        "",
        f"Scanned: {p.get('scanned_at')} ({p.get('event_type')})",
        f"Site:    {p.get('site_id') or '-'}{site_note}    Device: {p.get('device_id') or '-'}",
        f"Where:   {where}",
        "",
        "Evidence:",
        *(f"  - {f['code']}: {f['message']}" for f in p["flags"]),
        "",
        f"Audit record: {p['audit']['pk']} #{p['audit']['seq']} (sha256 {p['audit']['record_hash']})",
        "Quarantine the pack and report it to EFDA.",
    ]
    return "\n".join(lines)
