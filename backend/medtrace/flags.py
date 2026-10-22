"""Risk flags raised while verifying a scan, and how they roll up into a verdict."""

from __future__ import annotations

from dataclasses import dataclass, field

INFO = "info"
WARNING = "warning"
CRITICAL = "critical"

PASS = "PASS"  # nothing wrong found
WARN = "WARN"  # usable, but the dispenser should look closer
FAIL = "FAIL"  # do not dispense


@dataclass(frozen=True)
class Flag:
    code: str
    severity: str
    message: str
    clone_indicator: bool = False  # evidence the serial has been copied
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "clone_indicator": self.clone_indicator,
        }
        if self.details:
            out["details"] = self.details
        return out


def verdict(flags: list[Flag]) -> str:
    severities = {f.severity for f in flags}
    if CRITICAL in severities:
        return FAIL
    if WARNING in severities:
        return WARN
    return PASS
