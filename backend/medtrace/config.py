"""Runtime settings, read from Lambda environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    table_name: str | None = None
    alert_topic_arn: str | None = None
    max_speed_kmh: float = 120.0
    min_distance_km: float = 2.0
    history_limit: int = 25
    near_expiry_days: int = 30
    metrics_namespace: str = "MedTraceET"
    cors_allow_origin: str = "*"
    require_auth: bool = True
    site_claim: str = "custom:site_id"
    visual_model_module: str | None = None
    visual_mismatch_below: float = 0.5
    visual_match_at: float = 0.8

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        defaults = cls()
        settings = cls(
            table_name=env.get("SCAN_TABLE_NAME") or None,
            alert_topic_arn=env.get("ALERT_TOPIC_ARN") or None,
            max_speed_kmh=_number(env, "MAX_PLAUSIBLE_SPEED_KMH", defaults.max_speed_kmh, float),
            min_distance_km=_number(env, "MIN_TRAVEL_DISTANCE_KM", defaults.min_distance_km, float),
            history_limit=_number(env, "HISTORY_LIMIT", defaults.history_limit, int),
            near_expiry_days=_number(env, "NEAR_EXPIRY_DAYS", defaults.near_expiry_days, int),
            metrics_namespace=env.get("METRICS_NAMESPACE") or defaults.metrics_namespace,
            cors_allow_origin=env.get("CORS_ALLOW_ORIGIN") or defaults.cors_allow_origin,
            require_auth=_flag(env, "REQUIRE_AUTH", defaults.require_auth),
            site_claim=env.get("SITE_ID_CLAIM") or defaults.site_claim,
            visual_model_module=env.get("VISUAL_MODEL_MODULE") or None,
            visual_mismatch_below=_number(env, "VISUAL_MISMATCH_BELOW", defaults.visual_mismatch_below, float),
            visual_match_at=_number(env, "VISUAL_MATCH_AT", defaults.visual_match_at, float),
        )
        if not settings.visual_mismatch_below <= settings.visual_match_at <= 1:
            raise ValueError("Visual thresholds must satisfy 0 < VISUAL_MISMATCH_BELOW <= VISUAL_MATCH_AT <= 1")
        return settings


def _number(env: Mapping[str, str], name: str, default, kind):
    raw = env.get(name)
    if raw in (None, ""):
        return default
    try:
        value = kind(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a {kind.__name__}, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"Environment variable {name} must be positive, got {raw!r}")
    return value


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = (env.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ValueError(f"Environment variable {name} must be true or false, got {env.get(name)!r}")
