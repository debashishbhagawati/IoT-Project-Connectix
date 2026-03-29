from urllib.parse import urlparse

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from .config import settings


def _resolve_db_name() -> str:
    parsed = urlparse(settings.MONGODB_URL)
    db_name = parsed.path.lstrip("/")
    return db_name or settings.MONGODB_DB_NAME


mongo_client = MongoClient(settings.MONGODB_URL)
db: Database = mongo_client[_resolve_db_name()]


def get_db() -> Database:
    return db


def ensure_indexes() -> None:
    db.patients.create_index([("email", ASCENDING)], unique=True)
    db.patients.create_index([("patient_uid", ASCENDING)], unique=True)

    db.doctors.create_index([("email", ASCENDING)], unique=True)
    db.doctors.create_index([("doctor_uid", ASCENDING)], unique=True)

    db.doctor_patient_requests.create_index(
        [("doctor_id", ASCENDING), ("patient_id", ASCENDING)],
        unique=True,
    )
    db.doctor_patient_requests.create_index([("status", ASCENDING)])

    db.vital_readings.create_index([("patient_id", ASCENDING), ("timestamp", ASCENDING)])

    db.alerts.create_index([("patient_id", ASCENDING), ("created_at", ASCENDING)])
    db.alerts.create_index([("doctor_id", ASCENDING), ("acknowledged", ASCENDING), ("created_at", ASCENDING)])

    db.messages.create_index([("patient_id", ASCENDING), ("doctor_id", ASCENDING), ("created_at", ASCENDING)])
