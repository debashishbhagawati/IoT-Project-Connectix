# VitalGuard

VitalGuard is a real-time remote patient monitoring platform with:
- A **Patient Web App**
- A **Doctor Web App**
- A **FastAPI Backend API**
- A separate **AI/ML Anomaly Detection Service**
- An **IoT Vitals Simulator** for test data

It is designed to stream continuous vitals, classify anomalies, generate emergency alerts, and support secure doctor-patient collaboration.

## What is implemented

### Patient app features
- Patient signup/login with medical details
- Profile view with emergency contact and health info
- Search doctors by name or doctor ID
- Send doctor-link requests
- Request status tracking (`pending`, `accepted`, `rejected`)
- Accepted doctors visible in profile
- Accepted doctors hidden from search results
- Live vitals feed charts (with units)
- Alert panel with summary counters (`Critical`, `Moderate`, `Stable`)
- Real-time alert updates
- Messaging with accepted doctors

### Doctor app features
- Doctor signup/login with qualification, department, experience, expertise
- Incoming patient request management (accept/reject)
- Patient list under the doctor with search + sort by patient ID
- Emergency triage split into:
  - `Critical (Emergency)`
  - `Moderate (Review Needed)`
- Click alert/patient to open report section
- Patient contact + emergency contact details visible in report panel
- Live patient vitals feed charts (with units)
- Dedicated WhatsApp-style messaging panel
- Real-time alerts, vitals, and chat updates

### Backend/API features
- JWT-based role auth (`patient`, `doctor`)
- MongoDB persistence (local MongoDB or MongoDB Atlas)
- Doctor-patient request workflow
- Role-protected vitals/messages/alerts endpoints
- Device-key-protected ingestion endpoint
- WebSocket channels for live data push
- Auto demo-data seeding for first run

### AI anomaly detection service features
- Separate microservice (`anomaly-service`) in FastAPI
- Random Forest classifier (`scikit-learn`) for severity prediction
- Severity classes: `low`, `medium`, `high`
- Returns:
  - `severity`
  - `anomaly_detected`
  - `confidence`
  - per-class `probabilities`
  - `findings`
  - `message`
  - `model_version`
- Optional internal API-key validation
- Backend fallback to rule-based logic if service is unavailable (configurable)

## How AI detection works

1. IoT vitals are posted to backend endpoint:
- `POST /api/vitals/ingest`

2. Backend forwards vital features to anomaly service:
- `POST {ANOMALY_SERVICE_URL}/predict`

3. AI service inference logic:
- Uses 6 vital features:
  - `heart_rate`
  - `spo2`
  - `temperature_c`
  - `systolic_bp`
  - `diastolic_bp`
  - `respiratory_rate`
- Trains a Random Forest on synthetic normal + anomaly scenarios at startup
- Produces class probabilities and predicted severity
- Also generates clinical-style findings text
- Final severity is conservatively resolved to the higher of:
  - model severity
  - findings-based severity

4. Backend consumes classifier output:
- If anomaly detected, creates patient and doctor alerts
- Broadcasts updates over WebSockets
- Returns detection metadata (`anomaly_source`, `model_version`, `confidence`)

5. Fallback behavior:
- If AI service fails and `ANOMALY_SERVICE_FALLBACK_TO_RULES=true`, backend uses rule-based detection automatically.

## Repository structure

```text
VitalGuard/
  backend/             # Main FastAPI app + MongoDB + auth + websockets
  anomaly-service/     # Separate ML inference service
  patient-web/         # React app for patient
  doctor-web/          # React app for doctor
```

## Tech stack

- Backend: FastAPI, PyMongo, JWT, WebSockets
- Database: MongoDB
- AI service: FastAPI, NumPy, scikit-learn (Random Forest)
- Frontend: React + Vite
- Simulator: Python + httpx

## Prerequisites

- Python 3.11+
- Node.js 18+
- npm
- MongoDB (local) OR MongoDB Atlas free tier

## Environment setup

### 1) Backend env
Create `backend/.env` (or copy from `backend/.env.example`):

```env
MONGODB_URL=mongodb://localhost:27017/iot_care
MONGODB_DB_NAME=iot_care
JWT_SECRET=replace-with-a-strong-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_MINUTES=1440
DEVICE_API_KEY=dev-device-key
PATIENT_WEB_URL=http://localhost:5173
DOCTOR_WEB_URL=http://localhost:5174
SIM_API_BASE=http://localhost:8000

ANOMALY_SERVICE_URL=http://localhost:8010
ANOMALY_SERVICE_TIMEOUT_SECONDS=4
ANOMALY_SERVICE_API_KEY=
ANOMALY_SERVICE_FALLBACK_TO_RULES=true
```

### 2) Anomaly service env
Create `anomaly-service/.env` (or copy from `anomaly-service/.env.example`):

```env
ANOMALY_SERVICE_API_KEY=
MODEL_RANDOM_SEED=42
TRAINING_SAMPLES=18000
```

## Run the project

Run services in this order.

### Step 1: Start anomaly service
```bash
cd /Users/debashishbhagawati/Documents/Playground/anomaly-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Health check:
```bash
curl http://localhost:8010/health
```

### Step 2: Start backend API
```bash
cd /Users/debashishbhagawati/Documents/Playground/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check:
```bash
curl http://localhost:8000/api/health
```

### Step 3: Start patient web app
```bash
cd /Users/debashishbhagawati/Documents/Playground/patient-web
npm install
npm run dev
```
Patient app: `http://localhost:5173`

### Step 4: Start doctor web app
```bash
cd /Users/debashishbhagawati/Documents/Playground/doctor-web
npm install
npm run dev
```
Doctor app: `http://localhost:5174`

### Step 5: Start IoT vitals simulator
```bash
cd /Users/debashishbhagawati/Documents/Playground/backend
source .venv/bin/activate
python simulator/vitals_simulator.py --interval 2 --anomaly-chance 0.18
```

Optional specific patients:
```bash
python simulator/vitals_simulator.py --patients P-ABC123 P-XYZ789 --interval 1.5
```

## Demo (dummy) user accounts

These are auto-seeded only when MongoDB collections are empty.

### Doctors
- `doctor1@example.com` / `demo123` (Dr. Asha Rao)
- `doctor2@example.com` / `demo123` (Dr. Vikram Singh)

### Patients
- `patient1@example.com` / `demo123` (Ravi Sharma)
- `patient2@example.com` / `demo123` (Nisha Gupta)
- `patient3@example.com` / `demo123` (Arjun Iyer)

Notes:
- `doctor_uid` and `patient_uid` are randomly generated at seed time.
- If DB already has users, seed is skipped.

## Key API groups

### Auth
- `POST /api/auth/patient/register`
- `POST /api/auth/patient/login`
- `POST /api/auth/doctor/register`
- `POST /api/auth/doctor/login`

### Patient
- `GET /api/patient/profile`
- `GET /api/patient/doctors/search`
- `POST /api/patient/doctor-requests`
- `GET /api/patient/doctor-requests`
- `GET /api/patient/accepted-doctors`
- `GET /api/patient/vitals`
- `GET /api/patient/alerts`
- `GET/POST /api/patient/messages/{doctor_uid}`

### Doctor
- `GET /api/doctor/profile`
- `GET /api/doctor/requests`
- `POST /api/doctor/requests/{request_id}/decision`
- `GET /api/doctor/patients`
- `GET /api/doctor/patients/{patient_uid}/vitals`
- `GET /api/doctor/patients/{patient_uid}/contact`
- `GET /api/doctor/emergency-alerts`
- `POST /api/doctor/emergency-alerts/{alert_id}/ack`
- `GET/POST /api/doctor/messages/{patient_uid}`

### Device/IoT
- `GET /api/device/patients` (requires `x-device-key`)
- `POST /api/vitals/ingest` (requires `x-device-key`)

### WebSockets
- `WS /ws/patient?token=...`
- `WS /ws/doctor?token=...`

## Troubleshooting

### `ModuleNotFoundError: No module named pydantic_settings` in anomaly service
- Service has fallback support now, but best fix is:
```bash
pip install -r requirements.txt
```

### Backend starts but login fails with bcrypt/passlib issue
- Reinstall pinned dependencies inside backend venv:
```bash
pip install -r requirements.txt --upgrade --force-reinstall
```

### Simulator cannot connect to backend (`ConnectError`)
- Ensure backend is running on port `8000`
- Check `SIM_API_BASE` in `backend/.env`

## Project name and branding

This repository is the **VitalGuard** implementation. Some internal package names/titles may still use legacy labels (`iot-care-platform`) but functionality belongs to VitalGuard.
