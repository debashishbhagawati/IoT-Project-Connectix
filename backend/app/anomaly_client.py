from types import SimpleNamespace
from typing import Any

import httpx

from .anomaly import detect_anomalies
from .config import settings

VALID_SEVERITIES = {"low", "medium", "high"}


def _rule_fallback(vitals: dict[str, Any]) -> dict[str, Any]:
    severity, findings, message = detect_anomalies(SimpleNamespace(**vitals))
    return {
        "severity": severity,
        "findings": findings,
        "message": message,
        "anomaly_detected": bool(findings),
        "confidence": None,
        "model_version": "rules-fallback-v1",
        "source": "rules_fallback",
    }


def _normalize_response(data: dict[str, Any]) -> dict[str, Any]:
    severity = str(data.get("severity", "low")).lower()
    findings = data.get("findings", [])
    message = data.get("message")

    if severity not in VALID_SEVERITIES:
        raise ValueError("Invalid severity returned by anomaly service.")
    if not isinstance(findings, list):
        raise ValueError("Invalid findings returned by anomaly service.")

    clean_findings = [str(item) for item in findings]
    if not message:
        message = "No anomalies detected." if not clean_findings else "; ".join(clean_findings)

    anomaly_detected = bool(data.get("anomaly_detected")) or severity != "low" or bool(clean_findings)
    return {
        "severity": severity,
        "findings": clean_findings,
        "message": str(message),
        "anomaly_detected": anomaly_detected,
        "confidence": data.get("confidence"),
        "model_version": data.get("model_version"),
        "source": "ml_service",
    }


async def classify_vitals(vitals: dict[str, Any]) -> dict[str, Any]:
    endpoint = f"{settings.ANOMALY_SERVICE_URL.rstrip('/')}/predict"
    headers = {}
    if settings.ANOMALY_SERVICE_API_KEY:
        headers["x-anomaly-key"] = settings.ANOMALY_SERVICE_API_KEY

    try:
        async with httpx.AsyncClient(timeout=settings.ANOMALY_SERVICE_TIMEOUT_SECONDS) as client:
            response = await client.post(endpoint, json=vitals, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected anomaly response.")
        return _normalize_response(payload)
    except Exception as exc:
        if settings.ANOMALY_SERVICE_FALLBACK_TO_RULES:
            fallback = _rule_fallback(vitals)
            fallback["service_error"] = str(exc)
            return fallback
        raise RuntimeError("Anomaly service unavailable and fallback disabled.") from exc
