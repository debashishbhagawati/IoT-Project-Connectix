import argparse
import asyncio
import os
import random
from datetime import datetime, timezone
from typing import Dict, List

import httpx
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

API_BASE = os.getenv("SIM_API_BASE", "http://localhost:8000")
DEVICE_KEY = os.getenv("DEVICE_API_KEY", "dev-device-key")
PATIENTS_URL = f"{API_BASE}/api/device/patients"
INGEST_URL = f"{API_BASE}/api/vitals/ingest"


def build_normal_reading(patient_uid: str) -> Dict:
    return {
        "patient_uid": patient_uid,
        "heart_rate": random.randint(65, 95),
        "spo2": random.randint(95, 99),
        "temperature_c": round(random.uniform(36.4, 37.4), 1),
        "systolic_bp": random.randint(108, 128),
        "diastolic_bp": random.randint(70, 84),
        "respiratory_rate": random.randint(12, 18),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def inject_anomaly(reading: Dict) -> Dict:
    variant = random.choice(
        [
            {"heart_rate": random.randint(130, 160)},
            {"spo2": random.randint(82, 90)},
            {"temperature_c": round(random.uniform(38.5, 40.2), 1)},
            {"systolic_bp": random.randint(145, 175), "diastolic_bp": random.randint(95, 115)},
            {"respiratory_rate": random.randint(26, 34)},
        ]
    )
    reading.update(variant)
    return reading


async def fetch_patients(client: httpx.AsyncClient, only_patients: List[str]) -> List[str]:
    if only_patients:
        return only_patients

    response = await client.get(PATIENTS_URL, headers={"x-device-key": DEVICE_KEY}, timeout=10.0)
    response.raise_for_status()
    return response.json()


async def send_reading(client: httpx.AsyncClient, reading: Dict) -> None:
    try:
        response = await client.post(
            INGEST_URL,
            json=reading,
            headers={"x-device-key": DEVICE_KEY},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        status = "ANOMALY" if payload.get("anomaly_detected") else "normal"
        print(
            f"[{reading['timestamp']}] patient={reading['patient_uid']} "
            f"HR={reading['heart_rate']} SpO2={reading['spo2']} state={status}"
        )
    except Exception as exc:
        print(f"Failed to send reading for {reading['patient_uid']}: {exc}")


async def run_simulation(interval_seconds: float, anomaly_chance: float, only_patients: List[str]) -> None:
    async with httpx.AsyncClient() as client:
        patients = await fetch_patients(client, only_patients)
        if not patients:
            print("No patients found to simulate.")
            return

        print(f"Simulating {len(patients)} patient(s): {', '.join(patients)}")
        while True:
            for patient_uid in patients:
                reading = build_normal_reading(patient_uid)
                if random.random() < anomaly_chance:
                    reading = inject_anomaly(reading)
                await send_reading(client, reading)
            await asyncio.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate continuous IoT vitals feed.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between each patient batch.")
    parser.add_argument("--anomaly-chance", type=float, default=0.18, help="Chance of anomaly per reading.")
    parser.add_argument(
        "--patients",
        nargs="*",
        default=[],
        help="Optional list of patient IDs (example: --patients P-ABC123 P-XYZ789).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run_simulation(
            interval_seconds=args.interval,
            anomaly_chance=args.anomaly_chance,
            only_patients=args.patients,
        )
    )
