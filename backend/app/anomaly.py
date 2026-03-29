from typing import List, Tuple


class VitalLike:
    heart_rate: int
    spo2: int
    temperature_c: float
    systolic_bp: int
    diastolic_bp: int
    respiratory_rate: int


def detect_anomalies(vital: VitalLike) -> Tuple[str, List[str], str]:
    findings: List[str] = []
    severity = "low"

    if vital.heart_rate < 50:
        findings.append(f"Low heart rate ({vital.heart_rate} bpm)")
        severity = max_severity(severity, "medium")
    elif vital.heart_rate > 120:
        findings.append(f"High heart rate ({vital.heart_rate} bpm)")
        severity = max_severity(severity, "high" if vital.heart_rate > 140 else "medium")

    if vital.spo2 < 92:
        findings.append(f"Low SpO2 ({vital.spo2}%)")
        severity = max_severity(severity, "high" if vital.spo2 < 88 else "medium")

    if vital.temperature_c > 38.0:
        findings.append(f"High temperature ({vital.temperature_c:.1f} C)")
        severity = max_severity(severity, "high" if vital.temperature_c >= 39.0 else "medium")

    if vital.systolic_bp > 140 or vital.diastolic_bp > 90:
        findings.append(f"High blood pressure ({vital.systolic_bp}/{vital.diastolic_bp} mmHg)")
        severity = max_severity(severity, "medium")

    if vital.systolic_bp < 90 or vital.diastolic_bp < 60:
        findings.append(f"Low blood pressure ({vital.systolic_bp}/{vital.diastolic_bp} mmHg)")
        severity = max_severity(severity, "medium")

    if vital.respiratory_rate < 10:
        findings.append(f"Low respiratory rate ({vital.respiratory_rate} rpm)")
        severity = max_severity(severity, "medium")
    elif vital.respiratory_rate > 24:
        findings.append(f"High respiratory rate ({vital.respiratory_rate} rpm)")
        severity = max_severity(severity, "high" if vital.respiratory_rate > 30 else "medium")

    message = "No anomalies detected." if not findings else "; ".join(findings)
    return severity, findings, message


def max_severity(current: str, new: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return new if order[new] > order[current] else current
