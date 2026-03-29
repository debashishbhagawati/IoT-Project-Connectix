from datetime import datetime
from uuid import uuid4

from pymongo.database import Database

from .security import hash_password


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:6].upper()}"


def seed_demo_data(db: Database) -> None:
    if db.doctors.count_documents({}) > 0 or db.patients.count_documents({}) > 0:
        return

    doctor_1 = {
        "doctor_uid": _uid("D"),
        "full_name": "Dr. Asha Rao",
        "email": "doctor1@example.com",
        "password_hash": hash_password("demo123"),
        "qualification": "MBBS, MD",
        "department": "Cardiology",
        "experience_years": 9,
        "expertises": "Critical care, heart rhythm disorders",
        "phone": "+919876500001",
        "created_at": datetime.utcnow(),
    }
    doctor_2 = {
        "doctor_uid": _uid("D"),
        "full_name": "Dr. Vikram Singh",
        "email": "doctor2@example.com",
        "password_hash": hash_password("demo123"),
        "qualification": "MBBS, DM",
        "department": "Pulmonology",
        "experience_years": 12,
        "expertises": "Respiratory emergencies",
        "phone": "+919876500002",
        "created_at": datetime.utcnow(),
    }

    patient_1 = {
        "patient_uid": _uid("P"),
        "full_name": "Ravi Sharma",
        "email": "patient1@example.com",
        "password_hash": hash_password("demo123"),
        "age": 34,
        "gender": "Male",
        "blood_group": "B+",
        "medical_history": "Mild hypertension",
        "phone": "+919900100001",
        "address": "Bangalore",
        "emergency_contact_name": "Meera Sharma",
        "emergency_contact_phone": "+919900100010",
        "created_at": datetime.utcnow(),
    }
    patient_2 = {
        "patient_uid": _uid("P"),
        "full_name": "Nisha Gupta",
        "email": "patient2@example.com",
        "password_hash": hash_password("demo123"),
        "age": 29,
        "gender": "Female",
        "blood_group": "O+",
        "medical_history": "No chronic conditions",
        "phone": "+919900100002",
        "address": "Pune",
        "emergency_contact_name": "Anil Gupta",
        "emergency_contact_phone": "+919900100020",
        "created_at": datetime.utcnow(),
    }
    patient_3 = {
        "patient_uid": _uid("P"),
        "full_name": "Arjun Iyer",
        "email": "patient3@example.com",
        "password_hash": hash_password("demo123"),
        "age": 41,
        "gender": "Male",
        "blood_group": "A+",
        "medical_history": "Asthma",
        "phone": "+919900100003",
        "address": "Chennai",
        "emergency_contact_name": "Divya Iyer",
        "emergency_contact_phone": "+919900100030",
        "created_at": datetime.utcnow(),
    }

    doctor_result = db.doctors.insert_many([doctor_1, doctor_2])
    patient_result = db.patients.insert_many([patient_1, patient_2, patient_3])

    doctor_ids = doctor_result.inserted_ids
    patient_ids = patient_result.inserted_ids

    now = datetime.utcnow()
    links = [
        {
            "doctor_id": doctor_ids[0],
            "patient_id": patient_ids[0],
            "status": "accepted",
            "requested_at": now,
            "updated_at": now,
        },
        {
            "doctor_id": doctor_ids[0],
            "patient_id": patient_ids[1],
            "status": "pending",
            "requested_at": now,
            "updated_at": now,
        },
        {
            "doctor_id": doctor_ids[1],
            "patient_id": patient_ids[2],
            "status": "accepted",
            "requested_at": now,
            "updated_at": now,
        },
    ]
    db.doctor_patient_requests.insert_many(links)
