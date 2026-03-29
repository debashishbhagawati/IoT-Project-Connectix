from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestClassifier

Severity = Literal["low", "medium", "high"]


try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        ANOMALY_SERVICE_API_KEY: str = ""
        MODEL_RANDOM_SEED: int = 42
        TRAINING_SAMPLES: int = 18000

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

except ModuleNotFoundError:

    def _load_dotenv_file(path: str = ".env") -> None:
        dotenv_path = Path(path)
        if not dotenv_path.exists():
            return
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

    class Settings:
        def __init__(self) -> None:
            _load_dotenv_file(".env")
            self.ANOMALY_SERVICE_API_KEY = os.getenv("ANOMALY_SERVICE_API_KEY", "")
            self.MODEL_RANDOM_SEED = int(os.getenv("MODEL_RANDOM_SEED", "42"))
            self.TRAINING_SAMPLES = int(os.getenv("TRAINING_SAMPLES", "18000"))


settings = Settings()

FEATURE_ORDER = [
    "heart_rate",
    "spo2",
    "temperature_c",
    "systolic_bp",
    "diastolic_bp",
    "respiratory_rate",
]

SEVERITY_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
SEVERITY_BY_CLASS = {0: "low", 1: "medium", 2: "high"}


class PredictIn(BaseModel):
    heart_rate: int = Field(..., ge=20, le=250)
    spo2: int = Field(..., ge=50, le=100)
    temperature_c: float = Field(..., ge=30.0, le=45.0)
    systolic_bp: int = Field(..., ge=60, le=250)
    diastolic_bp: int = Field(..., ge=30, le=180)
    respiratory_rate: int = Field(..., ge=4, le=80)


class PredictOut(BaseModel):
    severity: Severity
    anomaly_detected: bool
    confidence: float
    probabilities: dict[str, float]
    findings: list[str]
    message: str
    model_version: str


def clamp_int(value: float, low: int, high: int) -> int:
    return int(max(low, min(high, round(value))))


def clamp_float(value: float, low: float, high: float, digits: int = 1) -> float:
    return round(max(low, min(high, value)), digits)


def max_severity(current: Severity, new: Severity) -> Severity:
    return new if SEVERITY_ORDER[new] > SEVERITY_ORDER[current] else current


def make_normal_reading(rng: np.random.Generator) -> dict[str, float]:
    return {
        "heart_rate": clamp_int(rng.normal(78, 9), 48, 112),
        "spo2": clamp_int(rng.normal(97, 1.1), 93, 100),
        "temperature_c": clamp_float(rng.normal(36.8, 0.3), 35.6, 37.7),
        "systolic_bp": clamp_int(rng.normal(118, 11), 94, 136),
        "diastolic_bp": clamp_int(rng.normal(76, 8), 58, 89),
        "respiratory_rate": clamp_int(rng.normal(16, 2.8), 10, 22),
    }


def make_anomaly_reading(rng: np.random.Generator) -> tuple[dict[str, float], int]:
    base = make_normal_reading(rng)
    scenario = rng.choice(
        [
            "tachycardia_medium",
            "tachycardia_high",
            "bradycardia",
            "hypoxia_medium",
            "hypoxia_high",
            "fever_medium",
            "fever_high",
            "hypertension",
            "hypotension",
            "respiratory_medium",
            "respiratory_high",
            "multi_critical",
        ]
    )

    if scenario == "tachycardia_medium":
        base["heart_rate"] = int(rng.integers(121, 141))
        return base, 1
    if scenario == "tachycardia_high":
        base["heart_rate"] = int(rng.integers(141, 181))
        return base, 2
    if scenario == "bradycardia":
        base["heart_rate"] = int(rng.integers(35, 50))
        return base, 1
    if scenario == "hypoxia_medium":
        base["spo2"] = int(rng.integers(88, 92))
        return base, 1
    if scenario == "hypoxia_high":
        base["spo2"] = int(rng.integers(74, 88))
        return base, 2
    if scenario == "fever_medium":
        base["temperature_c"] = clamp_float(rng.uniform(38.1, 38.9), 30.0, 45.0)
        return base, 1
    if scenario == "fever_high":
        base["temperature_c"] = clamp_float(rng.uniform(39.0, 40.7), 30.0, 45.0)
        return base, 2
    if scenario == "hypertension":
        base["systolic_bp"] = int(rng.integers(142, 186))
        base["diastolic_bp"] = int(rng.integers(92, 116))
        return base, 1
    if scenario == "hypotension":
        base["systolic_bp"] = int(rng.integers(70, 90))
        base["diastolic_bp"] = int(rng.integers(40, 60))
        return base, 1
    if scenario == "respiratory_medium":
        if rng.random() < 0.5:
            base["respiratory_rate"] = int(rng.integers(24, 31))
        else:
            base["respiratory_rate"] = int(rng.integers(8, 10))
        return base, 1
    if scenario == "respiratory_high":
        base["respiratory_rate"] = int(rng.integers(31, 42))
        return base, 2

    base["heart_rate"] = int(rng.integers(145, 185))
    base["spo2"] = int(rng.integers(72, 86))
    base["temperature_c"] = clamp_float(rng.uniform(39.2, 40.6), 30.0, 45.0)
    base["respiratory_rate"] = int(rng.integers(30, 40))
    return base, 2


def build_training_data(size: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    X: list[list[float]] = []
    y: list[int] = []

    for _ in range(size):
        if rng.random() < 0.65:
            row = make_normal_reading(rng)
            label = 0
        else:
            row, label = make_anomaly_reading(rng)
        X.append([float(row[key]) for key in FEATURE_ORDER])
        y.append(label)

    # Guard against tiny sample configurations that might miss one class.
    seeded_rows = [
        ({"heart_rate": 78, "spo2": 98, "temperature_c": 36.8, "systolic_bp": 118, "diastolic_bp": 76, "respiratory_rate": 16}, 0),
        ({"heart_rate": 132, "spo2": 90, "temperature_c": 38.4, "systolic_bp": 150, "diastolic_bp": 96, "respiratory_rate": 26}, 1),
        ({"heart_rate": 162, "spo2": 82, "temperature_c": 39.8, "systolic_bp": 176, "diastolic_bp": 114, "respiratory_rate": 34}, 2),
    ]
    for row, label in seeded_rows:
        X.append([float(row[key]) for key in FEATURE_ORDER])
        y.append(label)

    return np.array(X, dtype=np.float64), np.array(y, dtype=np.int64)


def extract_findings(reading: PredictIn) -> tuple[list[str], Severity]:
    findings: list[str] = []
    sev: Severity = "low"

    if reading.heart_rate < 50:
        findings.append(f"Low heart rate ({reading.heart_rate} bpm)")
        sev = max_severity(sev, "medium")
    elif reading.heart_rate > 120:
        findings.append(f"High heart rate ({reading.heart_rate} bpm)")
        sev = max_severity(sev, "high" if reading.heart_rate > 140 else "medium")

    if reading.spo2 < 92:
        findings.append(f"Low SpO2 ({reading.spo2}%)")
        sev = max_severity(sev, "high" if reading.spo2 < 88 else "medium")

    if reading.temperature_c > 38.0:
        findings.append(f"High temperature ({reading.temperature_c:.1f} C)")
        sev = max_severity(sev, "high" if reading.temperature_c >= 39.0 else "medium")

    if reading.systolic_bp > 140 or reading.diastolic_bp > 90:
        findings.append(f"High blood pressure ({reading.systolic_bp}/{reading.diastolic_bp} mmHg)")
        sev = max_severity(sev, "medium")

    if reading.systolic_bp < 90 or reading.diastolic_bp < 60:
        findings.append(f"Low blood pressure ({reading.systolic_bp}/{reading.diastolic_bp} mmHg)")
        sev = max_severity(sev, "medium")

    if reading.respiratory_rate < 10:
        findings.append(f"Low respiratory rate ({reading.respiratory_rate} rpm)")
        sev = max_severity(sev, "medium")
    elif reading.respiratory_rate > 24:
        findings.append(f"High respiratory rate ({reading.respiratory_rate} rpm)")
        sev = max_severity(sev, "high" if reading.respiratory_rate > 30 else "medium")

    return findings, sev


def build_model(seed: int, training_samples: int) -> tuple[RandomForestClassifier, str]:
    X, y = build_training_data(training_samples, seed)
    model = RandomForestClassifier(
        n_estimators=260,
        max_depth=12,
        min_samples_leaf=2,
        random_state=seed,
        n_jobs=1,
    )
    model.fit(X, y)
    return model, f"rf-v1-seed{seed}-n{training_samples}"


MODEL, MODEL_VERSION = build_model(settings.MODEL_RANDOM_SEED, settings.TRAINING_SAMPLES)
app = FastAPI(title="IoT Anomaly Classifier Service", version="1.0.0")


def verify_internal_key(x_anomaly_key: str = Header(default="")) -> None:
    if settings.ANOMALY_SERVICE_API_KEY and x_anomaly_key != settings.ANOMALY_SERVICE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid anomaly service key.")


def class_probabilities(model: RandomForestClassifier, probs: np.ndarray) -> dict[str, float]:
    items: dict[str, float] = {"low": 0.0, "medium": 0.0, "high": 0.0}
    for idx, cls in enumerate(model.classes_):
        label = SEVERITY_BY_CLASS[int(cls)]
        items[label] = float(probs[idx])
    return items


def pick_predicted_label(model: RandomForestClassifier, probs: np.ndarray) -> Severity:
    class_id = int(model.classes_[int(np.argmax(probs))])
    return SEVERITY_BY_CLASS[class_id]


def to_feature_vector(payload: PredictIn) -> np.ndarray:
    return np.array(
        [[float(getattr(payload, key)) for key in FEATURE_ORDER]],
        dtype=np.float64,
    )


def resolve_final_severity(model_severity: Severity, findings_severity: Severity) -> Severity:
    if SEVERITY_ORDER[findings_severity] > SEVERITY_ORDER[model_severity]:
        return findings_severity
    return model_severity


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "anomaly-ml", "model_version": MODEL_VERSION}


@app.post("/predict", response_model=PredictOut, dependencies=[Depends(verify_internal_key)])
def predict(payload: PredictIn) -> PredictOut:
    vector = to_feature_vector(payload)
    raw_probs = MODEL.predict_proba(vector)[0]
    probs = class_probabilities(MODEL, raw_probs)
    model_severity = pick_predicted_label(MODEL, raw_probs)
    findings, findings_severity = extract_findings(payload)
    severity = resolve_final_severity(model_severity, findings_severity)

    anomaly_detected = severity != "low" or bool(findings)
    if anomaly_detected and not findings:
        findings = ["Model flagged an abnormal combined-vitals pattern."]

    if anomaly_detected:
        message = "; ".join(findings)
    else:
        message = "No anomalies detected."

    if severity == model_severity:
        confidence = probs.get(severity, 0.0)
    else:
        confidence = max(probs.get(severity, 0.0), 0.65)

    return PredictOut(
        severity=severity,
        anomaly_detected=anomaly_detected,
        confidence=round(float(confidence), 4),
        probabilities={key: round(value, 4) for key, value in probs.items()},
        findings=findings,
        message=message,
        model_version=MODEL_VERSION,
    )
