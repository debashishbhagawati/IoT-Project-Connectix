# IoT Care Platform (Patient + Doctor Websites)

This project includes:
- `backend/` FastAPI API with MongoDB persistence, auth, doctor-patient request workflow, emergency alerts, and chat
- `anomaly-service/` FastAPI ML classifier service for anomaly scoring
- `patient-web/` React website for patients
- `doctor-web/` React website for doctors
- `backend/simulator/vitals_simulator.py` IoT vitals feed simulator

## Features Implemented

### Patient website
- Patient registration with medical details
- Patient login
- Search doctor by name or doctor ID
- Send doctor-add request
- See request status updates (pending/accepted/rejected)
- Live vitals monitoring feed
- Patient emergency alerts for anomalies
- Patient-doctor messaging

### Doctor website
- Doctor registration with qualification, department, experience, expertise (optional fields supported)
- Doctor login
- Incoming patient request review (accept/reject)
- Patient list under doctor with search + sort by patient ID
- Emergency section for high-priority alerts
- Click alert to view patient contact/emergency details
- Doctor-patient messaging

### Backend + IoT
- JWT auth for patient and doctor roles
- MongoDB database (local or Atlas free tier)
- Device-key-protected vitals ingestion endpoint
- Real-time websocket updates for alerts/vitals/messages
- External ML-based anomaly classification service and alert creation

## Tech Stack
- Backend: Python, FastAPI, PyMongo, MongoDB
- Anomaly service: Python, FastAPI, scikit-learn (Random Forest)
- Frontend: React + Vite (two separate apps)
- IoT simulation: Python script with `httpx`

## Environment Setup

Create and edit:
- `backend/.env` (already created with defaults)
- `backend/.env.example` (template)

Important env vars:
- `MONGODB_URL`
- `MONGODB_DB_NAME`
- `JWT_SECRET`
- `DEVICE_API_KEY`
- `PATIENT_WEB_URL`
- `DOCTOR_WEB_URL`
- `ANOMALY_SERVICE_URL`
- `ANOMALY_SERVICE_API_KEY`
- `ANOMALY_SERVICE_FALLBACK_TO_RULES`

### MongoDB options

1. Local MongoDB (free):
- `MONGODB_URL=mongodb://localhost:27017/iot_care`

2. MongoDB Atlas free tier (M0):
- `MONGODB_URL=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/iot_care`

## Run Anomaly Service (ML)

Open terminal 1:

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

## Run Backend

Open terminal 2:

```bash
cd /Users/debashishbhagawati/Documents/Playground/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Run Patient Website

```bash
cd /Users/debashishbhagawati/Documents/Playground/patient-web
npm install
npm run dev
```

Runs at: `http://localhost:5173`

## Run Doctor Website

```bash
cd /Users/debashishbhagawati/Documents/Playground/doctor-web
npm install
npm run dev
```

Runs at: `http://localhost:5174`

## Run IoT Simulator

Open another terminal:

```bash
cd /Users/debashishbhagawati/Documents/Playground/backend
source .venv/bin/activate
python simulator/vitals_simulator.py --interval 2 --anomaly-chance 0.18
```

Optional specific patients:

```bash
python simulator/vitals_simulator.py --patients P-ABC123 P-XYZ789 --interval 1.5
```

## Demo Accounts Seeded Automatically

On first backend start (empty DB), demo accounts are seeded:
- Patient login examples:
  - `patient1@example.com` / `demo123`
  - `patient2@example.com` / `demo123`
- Doctor login examples:
  - `doctor1@example.com` / `demo123`
  - `doctor2@example.com` / `demo123`

You can also create your own accounts from both websites.

## Main API Groups

- Auth:
  - `POST /api/auth/patient/register`
  - `POST /api/auth/patient/login`
  - `POST /api/auth/doctor/register`
  - `POST /api/auth/doctor/login`
- Patient actions:
  - `GET /api/patient/doctors/search`
  - `POST /api/patient/doctor-requests`
  - `GET /api/patient/doctor-requests`
  - `GET /api/patient/accepted-doctors`
  - `GET /api/patient/vitals`
  - `GET /api/patient/alerts`
  - `GET/POST /api/patient/messages/{doctor_uid}`
- Doctor actions:
  - `GET /api/doctor/requests`
  - `POST /api/doctor/requests/{request_id}/decision`
  - `GET /api/doctor/patients`
  - `GET /api/doctor/patients/{patient_uid}/vitals`
  - `GET /api/doctor/patients/{patient_uid}/contact`
  - `GET /api/doctor/emergency-alerts`
  - `POST /api/doctor/emergency-alerts/{alert_id}/ack`
  - `GET/POST /api/doctor/messages/{patient_uid}`
- Device/IoT:
  - `GET /api/device/patients` (requires `x-device-key`)
  - `POST /api/vitals/ingest` (requires `x-device-key`)
- WebSockets:
  - `WS /ws/patient?token=...`
  - `WS /ws/doctor?token=...`
