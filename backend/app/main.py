from datetime import datetime, timezone
from uuid import uuid4
import re

from bson import ObjectId
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from .anomaly_client import classify_vitals
from .config import settings
from .connections import ConnectionManager
from .mongo import ensure_indexes, get_db
from .schemas import (
    DoctorRegisterIn,
    DoctorRequestIn,
    LoginIn,
    MessageIn,
    PatientRegisterIn,
    RequestDecisionIn,
    VitalIngestIn,
)
from .security import create_access_token, decode_access_token, hash_password, verify_password
from .seed import seed_demo_data

app = FastAPI(title="IoT Care Platform API", version="3.0.0")
manager = ConnectionManager()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
db = get_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.PATIENT_WEB_URL, settings.DOCTOR_WEB_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_indexes()
    seed_demo_data(db)


def now_utc_naive() -> datetime:
    return datetime.utcnow()


def format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat()


def oid(value: str, field_name: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}.") from exc


def generate_unique_uid(collection, field: str, prefix: str) -> str:
    while True:
        candidate = f"{prefix}-{uuid4().hex[:6].upper()}"
        if collection.count_documents({field: candidate}, limit=1) == 0:
            return candidate


def serialize_patient(patient: dict, include_medical: bool = False) -> dict:
    payload = {
        "patient_uid": patient.get("patient_uid"),
        "full_name": patient.get("full_name"),
        "email": patient.get("email"),
        "phone": patient.get("phone"),
        "age": patient.get("age"),
        "gender": patient.get("gender"),
        "blood_group": patient.get("blood_group"),
        "created_at": format_dt(patient.get("created_at")),
    }
    if include_medical:
        payload.update(
            {
                "medical_history": patient.get("medical_history"),
                "address": patient.get("address"),
                "emergency_contact_name": patient.get("emergency_contact_name"),
                "emergency_contact_phone": patient.get("emergency_contact_phone"),
            }
        )
    return payload


def serialize_doctor(doctor: dict) -> dict:
    return {
        "doctor_uid": doctor.get("doctor_uid"),
        "full_name": doctor.get("full_name"),
        "email": doctor.get("email"),
        "qualification": doctor.get("qualification"),
        "department": doctor.get("department"),
        "experience_years": doctor.get("experience_years"),
        "expertises": doctor.get("expertises"),
        "phone": doctor.get("phone"),
        "created_at": format_dt(doctor.get("created_at")),
    }


def serialize_vital(vital: dict, patient_uid: str) -> dict:
    return {
        "id": str(vital.get("_id")),
        "patient_uid": patient_uid,
        "heart_rate": vital.get("heart_rate"),
        "spo2": vital.get("spo2"),
        "temperature_c": vital.get("temperature_c"),
        "systolic_bp": vital.get("systolic_bp"),
        "diastolic_bp": vital.get("diastolic_bp"),
        "respiratory_rate": vital.get("respiratory_rate"),
        "timestamp": format_dt(vital.get("timestamp")),
    }


def serialize_alert(alert: dict, patient: dict) -> dict:
    return {
        "id": str(alert.get("_id")),
        "patient_uid": patient.get("patient_uid"),
        "patient_name": patient.get("full_name"),
        "severity": alert.get("severity"),
        "message": alert.get("message"),
        "metrics": alert.get("metrics", []),
        "acknowledged": alert.get("acknowledged", False),
        "created_at": format_dt(alert.get("created_at")),
    }


def serialize_message(message: dict, patient_uid: str, doctor_uid: str) -> dict:
    return {
        "id": str(message.get("_id")),
        "patient_uid": patient_uid,
        "doctor_uid": doctor_uid,
        "sender_role": message.get("sender_role"),
        "sender_id": str(message.get("sender_id")),
        "content": message.get("content"),
        "created_at": format_dt(message.get("created_at")),
    }


def get_payload(token: str = Depends(oauth2_scheme)) -> dict:
    return decode_access_token(token)


def get_current_patient(payload: dict = Depends(get_payload)) -> dict:
    if payload.get("role") != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patient access required.")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    patient = db.patients.find_one({"_id": oid(user_id, "user_id")})
    if not patient:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Patient not found.")
    return patient


def get_current_doctor(payload: dict = Depends(get_payload)) -> dict:
    if payload.get("role") != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doctor access required.")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    doctor = db.doctors.find_one({"_id": oid(user_id, "user_id")})
    if not doctor:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Doctor not found.")
    return doctor


def get_doctor_by_uid(doctor_uid: str) -> dict:
    doctor = db.doctors.find_one({"doctor_uid": doctor_uid})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    return doctor


def get_patient_by_uid(patient_uid: str) -> dict:
    patient = db.patients.find_one({"patient_uid": patient_uid})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return patient


def ensure_active_link(doctor_id: ObjectId, patient_id: ObjectId) -> None:
    link = db.doctor_patient_requests.find_one(
        {
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "status": "accepted",
        }
    )
    if not link:
        raise HTTPException(status_code=403, detail="Doctor-patient link not active.")


def require_device_key(x_device_key: str = Header(default="")) -> None:
    if x_device_key != settings.DEVICE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid device key.")


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok", "service": "iot-care-platform", "database": "mongodb"}


@app.post("/api/auth/patient/register")
def patient_register(payload: PatientRegisterIn) -> dict:
    email = payload.email.strip().lower()
    if db.patients.count_documents({"email": email}, limit=1) > 0 or db.doctors.count_documents({"email": email}, limit=1) > 0:
        raise HTTPException(status_code=400, detail="Email already in use.")

    patient_uid = generate_unique_uid(db.patients, "patient_uid", "P")
    patient_doc = {
        "patient_uid": patient_uid,
        "full_name": payload.full_name.strip(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "age": payload.age,
        "gender": payload.gender,
        "blood_group": payload.blood_group,
        "medical_history": payload.medical_history,
        "phone": payload.phone,
        "address": payload.address,
        "emergency_contact_name": payload.emergency_contact_name,
        "emergency_contact_phone": payload.emergency_contact_phone,
        "created_at": now_utc_naive(),
    }

    try:
        result = db.patients.insert_one(patient_doc)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=400, detail="Patient already exists.") from exc

    patient = db.patients.find_one({"_id": result.inserted_id})
    token = create_access_token(role="patient", user_id=str(result.inserted_id))
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "patient",
        "user": serialize_patient(patient, include_medical=True),
    }


@app.post("/api/auth/patient/login")
def patient_login(payload: LoginIn) -> dict:
    email = payload.email.strip().lower()
    patient = db.patients.find_one({"email": email})
    if not patient or not verify_password(payload.password, patient.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    token = create_access_token(role="patient", user_id=str(patient["_id"]))
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "patient",
        "user": serialize_patient(patient, include_medical=True),
    }


@app.post("/api/auth/doctor/register")
def doctor_register(payload: DoctorRegisterIn) -> dict:
    email = payload.email.strip().lower()
    if db.doctors.count_documents({"email": email}, limit=1) > 0 or db.patients.count_documents({"email": email}, limit=1) > 0:
        raise HTTPException(status_code=400, detail="Email already in use.")

    doctor_uid = generate_unique_uid(db.doctors, "doctor_uid", "D")
    doctor_doc = {
        "doctor_uid": doctor_uid,
        "full_name": payload.full_name.strip(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "qualification": payload.qualification,
        "department": payload.department,
        "experience_years": payload.experience_years,
        "expertises": payload.expertises,
        "phone": payload.phone,
        "created_at": now_utc_naive(),
    }

    try:
        result = db.doctors.insert_one(doctor_doc)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=400, detail="Doctor already exists.") from exc

    doctor = db.doctors.find_one({"_id": result.inserted_id})
    token = create_access_token(role="doctor", user_id=str(result.inserted_id))
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "doctor",
        "user": serialize_doctor(doctor),
    }


@app.post("/api/auth/doctor/login")
def doctor_login(payload: LoginIn) -> dict:
    email = payload.email.strip().lower()
    doctor = db.doctors.find_one({"email": email})
    if not doctor or not verify_password(payload.password, doctor.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    token = create_access_token(role="doctor", user_id=str(doctor["_id"]))
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "doctor",
        "user": serialize_doctor(doctor),
    }


@app.get("/api/patient/profile")
def patient_profile(current: dict = Depends(get_current_patient)) -> dict:
    return serialize_patient(current, include_medical=True)


@app.get("/api/doctor/profile")
def doctor_profile(current: dict = Depends(get_current_doctor)) -> dict:
    return serialize_doctor(current)


@app.get("/api/patient/doctors/search")
def patient_search_doctors(
    q: str = Query(default=""),
    current: dict = Depends(get_current_patient),
) -> list[dict]:
    del current

    search = q.strip()
    query = {}
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        query = {"$or": [{"full_name": pattern}, {"doctor_uid": pattern}]}

    doctors = db.doctors.find(query).sort("full_name", ASCENDING).limit(50)
    return [serialize_doctor(item) for item in doctors]


@app.post("/api/patient/doctor-requests")
async def patient_send_doctor_request(
    payload: DoctorRequestIn,
    current: dict = Depends(get_current_patient),
) -> dict:
    doctor = get_doctor_by_uid(payload.doctor_uid)

    existing = db.doctor_patient_requests.find_one(
        {
            "doctor_id": doctor["_id"],
            "patient_id": current["_id"],
        }
    )

    now = now_utc_naive()
    if existing:
        if existing.get("status") == "accepted":
            raise HTTPException(status_code=400, detail="Doctor is already linked to this patient.")

        db.doctor_patient_requests.update_one(
            {"_id": existing["_id"]},
            {"$set": {"status": "pending", "updated_at": now}},
        )
        request_row = db.doctor_patient_requests.find_one({"_id": existing["_id"]})
    else:
        result = db.doctor_patient_requests.insert_one(
            {
                "doctor_id": doctor["_id"],
                "patient_id": current["_id"],
                "status": "pending",
                "requested_at": now,
                "updated_at": now,
            }
        )
        request_row = db.doctor_patient_requests.find_one({"_id": result.inserted_id})

    request_payload = {
        "id": str(request_row["_id"]),
        "status": request_row.get("status"),
        "requested_at": format_dt(request_row.get("requested_at")),
        "updated_at": format_dt(request_row.get("updated_at")),
        "doctor": serialize_doctor(doctor),
        "patient": serialize_patient(current, include_medical=False),
    }
    await manager.broadcast_doctor(str(doctor["_id"]), {"type": "doctor_request", "data": request_payload})
    return request_payload


@app.get("/api/patient/doctor-requests")
def patient_list_requests(current: dict = Depends(get_current_patient)) -> list[dict]:
    rows = []
    cursor = db.doctor_patient_requests.find({"patient_id": current["_id"]}).sort("updated_at", DESCENDING)
    for request_row in cursor:
        doctor = db.doctors.find_one({"_id": request_row.get("doctor_id")})
        if not doctor:
            continue
        rows.append(
            {
                "id": str(request_row["_id"]),
                "status": request_row.get("status"),
                "requested_at": format_dt(request_row.get("requested_at")),
                "updated_at": format_dt(request_row.get("updated_at")),
                "doctor": serialize_doctor(doctor),
            }
        )
    return rows


@app.get("/api/patient/accepted-doctors")
def patient_accepted_doctors(current: dict = Depends(get_current_patient)) -> list[dict]:
    links = list(
        db.doctor_patient_requests.find(
            {
                "patient_id": current["_id"],
                "status": "accepted",
            }
        )
    )
    doctor_ids = [link.get("doctor_id") for link in links if link.get("doctor_id") is not None]
    if not doctor_ids:
        return []

    doctors = db.doctors.find({"_id": {"$in": doctor_ids}}).sort("full_name", ASCENDING)
    return [serialize_doctor(item) for item in doctors]


@app.get("/api/doctor/requests")
def doctor_incoming_requests(
    status_filter: str = Query(default="pending", alias="status"),
    current: dict = Depends(get_current_doctor),
) -> list[dict]:
    query = {"doctor_id": current["_id"]}
    if status_filter in {"pending", "accepted", "rejected"}:
        query["status"] = status_filter

    rows = []
    cursor = db.doctor_patient_requests.find(query).sort("updated_at", DESCENDING)
    for request_row in cursor:
        patient = db.patients.find_one({"_id": request_row.get("patient_id")})
        if not patient:
            continue
        rows.append(
            {
                "id": str(request_row["_id"]),
                "status": request_row.get("status"),
                "requested_at": format_dt(request_row.get("requested_at")),
                "updated_at": format_dt(request_row.get("updated_at")),
                "patient": serialize_patient(patient, include_medical=True),
            }
        )
    return rows


@app.post("/api/doctor/requests/{request_id}/decision")
async def doctor_decide_request(
    request_id: str,
    payload: RequestDecisionIn,
    current: dict = Depends(get_current_doctor),
) -> dict:
    request_obj_id = oid(request_id, "request_id")
    request_row = db.doctor_patient_requests.find_one({"_id": request_obj_id, "doctor_id": current["_id"]})
    if not request_row:
        raise HTTPException(status_code=404, detail="Request not found.")

    status_value = "accepted" if payload.action == "accept" else "rejected"
    db.doctor_patient_requests.update_one(
        {"_id": request_obj_id},
        {"$set": {"status": status_value, "updated_at": now_utc_naive()}},
    )
    request_row = db.doctor_patient_requests.find_one({"_id": request_obj_id})

    patient = db.patients.find_one({"_id": request_row.get("patient_id")})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    response_payload = {
        "id": str(request_row["_id"]),
        "status": request_row.get("status"),
        "requested_at": format_dt(request_row.get("requested_at")),
        "updated_at": format_dt(request_row.get("updated_at")),
        "patient": serialize_patient(patient, include_medical=True),
    }
    await manager.broadcast_patient(str(patient["_id"]), {"type": "doctor_request_update", "data": response_payload})
    return response_payload


@app.get("/api/doctor/patients")
def doctor_patients(
    sort: str = Query(default="asc", pattern="^(asc|desc)$"),
    query: str = Query(default=""),
    current: dict = Depends(get_current_doctor),
) -> list[dict]:
    links = list(
        db.doctor_patient_requests.find(
            {
                "doctor_id": current["_id"],
                "status": "accepted",
            }
        )
    )
    patient_ids = [link.get("patient_id") for link in links if link.get("patient_id") is not None]
    if not patient_ids:
        return []

    patient_filter: dict = {"_id": {"$in": patient_ids}}
    if query.strip():
        patient_filter["patient_uid"] = {"$regex": re.escape(query.strip()), "$options": "i"}

    sort_order = DESCENDING if sort == "desc" else ASCENDING
    rows = db.patients.find(patient_filter).sort("patient_uid", sort_order)
    return [serialize_patient(item, include_medical=False) for item in rows]


@app.get("/api/patient/vitals")
def patient_vitals(
    limit: int = Query(default=60, ge=1, le=500),
    current: dict = Depends(get_current_patient),
) -> list[dict]:
    rows = list(
        db.vital_readings.find({"patient_id": current["_id"]})
        .sort("timestamp", DESCENDING)
        .limit(limit)
    )
    rows.reverse()
    return [serialize_vital(item, current.get("patient_uid")) for item in rows]


@app.get("/api/doctor/patients/{patient_uid}/vitals")
def doctor_patient_vitals(
    patient_uid: str,
    limit: int = Query(default=80, ge=1, le=500),
    current: dict = Depends(get_current_doctor),
) -> list[dict]:
    patient = get_patient_by_uid(patient_uid)
    ensure_active_link(current["_id"], patient["_id"])

    rows = list(
        db.vital_readings.find({"patient_id": patient["_id"]})
        .sort("timestamp", DESCENDING)
        .limit(limit)
    )
    rows.reverse()
    return [serialize_vital(item, patient.get("patient_uid")) for item in rows]


@app.get("/api/patient/alerts")
def patient_alerts(
    limit: int = Query(default=60, ge=1, le=500),
    current: dict = Depends(get_current_patient),
) -> list[dict]:
    rows = db.alerts.find({"patient_id": current["_id"], "doctor_id": None}).sort("created_at", DESCENDING).limit(limit)
    return [serialize_alert(item, current) for item in rows]


@app.get("/api/doctor/emergency-alerts")
def doctor_emergency_alerts(
    limit: int = Query(default=100, ge=1, le=500),
    include_acknowledged: bool = Query(default=False),
    current: dict = Depends(get_current_doctor),
) -> list[dict]:
    query = {"doctor_id": current["_id"]}
    if not include_acknowledged:
        query["acknowledged"] = False

    rows = []
    cursor = db.alerts.find(query).sort("created_at", DESCENDING).limit(limit)
    for alert in cursor:
        patient = db.patients.find_one({"_id": alert.get("patient_id")})
        if patient:
            rows.append(serialize_alert(alert, patient))
    return rows


@app.post("/api/doctor/emergency-alerts/{alert_id}/ack")
def doctor_ack_alert(
    alert_id: str,
    current: dict = Depends(get_current_doctor),
) -> dict:
    alert_obj_id = oid(alert_id, "alert_id")
    result = db.alerts.update_one(
        {"_id": alert_obj_id, "doctor_id": current["_id"]},
        {"$set": {"acknowledged": True}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found.")

    return {"ok": True, "alert_id": alert_id}


@app.get("/api/doctor/patients/{patient_uid}/contact")
def doctor_patient_contact(
    patient_uid: str,
    current: dict = Depends(get_current_doctor),
) -> dict:
    patient = get_patient_by_uid(patient_uid)
    ensure_active_link(current["_id"], patient["_id"])

    return {
        "patient_uid": patient.get("patient_uid"),
        "full_name": patient.get("full_name"),
        "phone": patient.get("phone"),
        "address": patient.get("address"),
        "emergency_contact_name": patient.get("emergency_contact_name"),
        "emergency_contact_phone": patient.get("emergency_contact_phone"),
    }


@app.get("/api/patient/messages/{doctor_uid}")
def patient_get_messages(
    doctor_uid: str,
    limit: int = Query(default=80, ge=1, le=300),
    current: dict = Depends(get_current_patient),
) -> list[dict]:
    doctor = get_doctor_by_uid(doctor_uid)
    ensure_active_link(doctor["_id"], current["_id"])

    rows = list(
        db.messages.find({"patient_id": current["_id"], "doctor_id": doctor["_id"]})
        .sort("created_at", DESCENDING)
        .limit(limit)
    )
    rows.reverse()
    return [serialize_message(item, current.get("patient_uid"), doctor.get("doctor_uid")) for item in rows]


@app.post("/api/patient/messages/{doctor_uid}")
async def patient_send_message(
    doctor_uid: str,
    payload: MessageIn,
    current: dict = Depends(get_current_patient),
) -> dict:
    doctor = get_doctor_by_uid(doctor_uid)
    ensure_active_link(doctor["_id"], current["_id"])

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    result = db.messages.insert_one(
        {
            "patient_id": current["_id"],
            "doctor_id": doctor["_id"],
            "sender_role": "patient",
            "sender_id": current["_id"],
            "content": content,
            "created_at": now_utc_naive(),
        }
    )
    message = db.messages.find_one({"_id": result.inserted_id})

    event_data = serialize_message(message, current.get("patient_uid"), doctor.get("doctor_uid"))
    await manager.broadcast_patient(str(current["_id"]), {"type": "message", "data": event_data})
    await manager.broadcast_doctor(str(doctor["_id"]), {"type": "message", "data": event_data})
    return event_data


@app.get("/api/doctor/messages/{patient_uid}")
def doctor_get_messages(
    patient_uid: str,
    limit: int = Query(default=80, ge=1, le=300),
    current: dict = Depends(get_current_doctor),
) -> list[dict]:
    patient = get_patient_by_uid(patient_uid)
    ensure_active_link(current["_id"], patient["_id"])

    rows = list(
        db.messages.find({"patient_id": patient["_id"], "doctor_id": current["_id"]})
        .sort("created_at", DESCENDING)
        .limit(limit)
    )
    rows.reverse()
    return [serialize_message(item, patient.get("patient_uid"), current.get("doctor_uid")) for item in rows]


@app.post("/api/doctor/messages/{patient_uid}")
async def doctor_send_message(
    patient_uid: str,
    payload: MessageIn,
    current: dict = Depends(get_current_doctor),
) -> dict:
    patient = get_patient_by_uid(patient_uid)
    ensure_active_link(current["_id"], patient["_id"])

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    result = db.messages.insert_one(
        {
            "patient_id": patient["_id"],
            "doctor_id": current["_id"],
            "sender_role": "doctor",
            "sender_id": current["_id"],
            "content": content,
            "created_at": now_utc_naive(),
        }
    )
    message = db.messages.find_one({"_id": result.inserted_id})

    event_data = serialize_message(message, patient.get("patient_uid"), current.get("doctor_uid"))
    await manager.broadcast_patient(str(patient["_id"]), {"type": "message", "data": event_data})
    await manager.broadcast_doctor(str(current["_id"]), {"type": "message", "data": event_data})
    return event_data


@app.get("/api/device/patients", dependencies=[Depends(require_device_key)])
def device_patients() -> list[str]:
    rows = db.patients.find({}, {"patient_uid": 1}).sort("patient_uid", ASCENDING)
    return [item.get("patient_uid") for item in rows if item.get("patient_uid")]


@app.post("/api/vitals/ingest", dependencies=[Depends(require_device_key)])
async def ingest_vitals(payload: VitalIngestIn) -> dict:
    patient = get_patient_by_uid(payload.patient_uid)

    if payload.timestamp is not None:
        if payload.timestamp.tzinfo is not None:
            timestamp = payload.timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            timestamp = payload.timestamp
    else:
        timestamp = now_utc_naive()

    vital_doc = {
        "patient_id": patient["_id"],
        "heart_rate": payload.heart_rate,
        "spo2": payload.spo2,
        "temperature_c": payload.temperature_c,
        "systolic_bp": payload.systolic_bp,
        "diastolic_bp": payload.diastolic_bp,
        "respiratory_rate": payload.respiratory_rate,
        "timestamp": timestamp,
    }
    vital_result = db.vital_readings.insert_one(vital_doc)
    vital = db.vital_readings.find_one({"_id": vital_result.inserted_id})

    assessment = await classify_vitals(
        {
            "heart_rate": payload.heart_rate,
            "spo2": payload.spo2,
            "temperature_c": payload.temperature_c,
            "systolic_bp": payload.systolic_bp,
            "diastolic_bp": payload.diastolic_bp,
            "respiratory_rate": payload.respiratory_rate,
        }
    )
    severity = assessment.get("severity", "low")
    findings = assessment.get("findings", [])
    message_text = assessment.get("message", "No anomalies detected.")

    links = list(
        db.doctor_patient_requests.find(
            {
                "patient_id": patient["_id"],
                "status": "accepted",
            }
        )
    )
    doctor_ids = [link.get("doctor_id") for link in links if link.get("doctor_id") is not None]

    patient_alert = None
    doctor_alerts: list[tuple[str, dict]] = []

    if findings:
        patient_alert_result = db.alerts.insert_one(
            {
                "patient_id": patient["_id"],
                "doctor_id": None,
                "severity": severity,
                "message": message_text,
                "metrics": findings,
                "acknowledged": False,
                "created_at": now_utc_naive(),
            }
        )
        patient_alert = db.alerts.find_one({"_id": patient_alert_result.inserted_id})

        for doctor_id in doctor_ids:
            alert_result = db.alerts.insert_one(
                {
                    "patient_id": patient["_id"],
                    "doctor_id": doctor_id,
                    "severity": severity,
                    "message": message_text,
                    "metrics": findings,
                    "acknowledged": False,
                    "created_at": now_utc_naive(),
                }
            )
            alert = db.alerts.find_one({"_id": alert_result.inserted_id})
            doctor_alerts.append((str(doctor_id), alert))

    vital_event = {"type": "vital_update", "data": serialize_vital(vital, patient.get("patient_uid"))}
    await manager.broadcast_patient(str(patient["_id"]), vital_event)
    for doctor_id in doctor_ids:
        await manager.broadcast_doctor(str(doctor_id), vital_event)

    if patient_alert is not None:
        await manager.broadcast_patient(
            str(patient["_id"]),
            {"type": "alert", "data": serialize_alert(patient_alert, patient)},
        )

    for doctor_id, doctor_alert in doctor_alerts:
        await manager.broadcast_doctor(
            doctor_id,
            {"type": "alert", "data": serialize_alert(doctor_alert, patient)},
        )

    return {
        "accepted": True,
        "patient_uid": patient.get("patient_uid"),
        "anomaly_detected": bool(assessment.get("anomaly_detected", bool(findings))),
        "severity": severity,
        "findings": findings,
        "anomaly_source": assessment.get("source"),
        "model_version": assessment.get("model_version"),
        "confidence": assessment.get("confidence"),
    }


def parse_ws_identity(token: str, expected_role: str) -> str:
    payload = decode_access_token(token)
    if payload.get("role") != expected_role:
        raise HTTPException(status_code=403, detail="Invalid websocket role.")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid websocket token.")

    oid(user_id, "user_id")
    return user_id


@app.websocket("/ws/patient")
async def patient_socket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    try:
        patient_id = parse_ws_identity(token, expected_role="patient")
    except HTTPException:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    patient = db.patients.find_one({"_id": oid(patient_id, "patient_id")})
    if not patient:
        await websocket.close(code=1008, reason="Unknown patient")
        return

    await manager.connect_patient(patient_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_patient(patient_id, websocket)


@app.websocket("/ws/doctor")
async def doctor_socket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    try:
        doctor_id = parse_ws_identity(token, expected_role="doctor")
    except HTTPException:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    doctor = db.doctors.find_one({"_id": oid(doctor_id, "doctor_id")})
    if not doctor:
        await websocket.close(code=1008, reason="Unknown doctor")
        return

    await manager.connect_doctor(doctor_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_doctor(doctor_id, websocket)
