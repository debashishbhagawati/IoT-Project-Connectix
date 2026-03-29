import { useEffect, useMemo, useState } from "react";
import {
  getAcceptedDoctors,
  getAlerts,
  getDoctorRequests,
  getMessages,
  getPatientProfile,
  getVitals,
  openPatientSocket,
  patientLogin,
  patientRegister,
  searchDoctors,
  sendDoctorRequest,
  sendMessage,
} from "./api";

const AUTH_KEY = "patient_portal_auth";
const MAX_VITALS = 120;

const METRICS = [
  { key: "heart_rate", label: "Heart Rate", unit: "bpm", color: "#ef4444", min: 40, max: 180 },
  { key: "spo2", label: "SpO2", unit: "%", color: "#2563eb", min: 80, max: 100 },
  { key: "temperature_c", label: "Temperature", unit: "C", color: "#ea580c", min: 35, max: 41 },
  { key: "respiratory_rate", label: "Respiratory", unit: "rpm", color: "#0891b2", min: 8, max: 36 },
];

function getStoredAuth() {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveAuth(payload) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(payload));
}

function clearAuth() {
  localStorage.removeItem(AUTH_KEY);
}

function fmt(dt) {
  return new Date(dt).toLocaleString();
}

function latest(vitals) {
  return vitals.length ? vitals[vitals.length - 1] : null;
}

function uniqueById(items) {
  const seen = new Set();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function severityClass(severity) {
  if (severity === "high") return "critical";
  if (severity === "medium") return "moderate";
  return "stable";
}

function MedicalVitalChart({ vitals, metricKey }) {
  const metric = METRICS.find((item) => item.key === metricKey) || METRICS[0];
  const series = vitals.slice(-70).map((item) => Number(item[metric.key] ?? 0));
  const width = 880;
  const height = 240;
  const padX = 20;
  const padY = 22;

  if (series.length < 2) {
    return (
      <div className="chart-shell">
        <p className="muted">Waiting for enough live points to plot graph.</p>
      </div>
    );
  }

  const minY = metric.min;
  const maxY = metric.max;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const points = series.map((value, index) => {
    const x = padX + (index / (series.length - 1)) * innerW;
    const clamped = Math.min(maxY, Math.max(minY, value));
    const y = padY + ((maxY - clamped) / (maxY - minY)) * innerH;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const yMarkers = [maxY, (maxY + minY) / 2, minY];
  const precision = metric.key === "temperature_c" ? 1 : 0;

  return (
    <div className="chart-shell">
      <svg viewBox={`0 0 ${width} ${height}`} className="medical-chart" role="img" aria-label="Medical live feed">
        <defs>
          <pattern id="ecg-grid-small" width="12" height="12" patternUnits="userSpaceOnUse">
            <path d="M 12 0 L 0 0 0 12" fill="none" stroke="#dce6f4" strokeWidth="1" />
          </pattern>
          <pattern id="ecg-grid-big" width="60" height="60" patternUnits="userSpaceOnUse">
            <rect width="60" height="60" fill="url(#ecg-grid-small)" />
            <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#bfd0e8" strokeWidth="1.2" />
          </pattern>
        </defs>
        <rect x="0" y="0" width={width} height={height} fill="url(#ecg-grid-big)" rx="10" />
        {yMarkers.map((value) => {
          const y = padY + ((maxY - value) / (maxY - minY)) * innerH;
          return (
            <g key={`mark-${value}`}>
              <line
                x1={padX}
                y1={y}
                x2={width - padX}
                y2={y}
                stroke="#9fb4cf"
                strokeWidth="0.6"
                strokeDasharray="3 4"
              />
              <text x={padX + 4} y={y - 4} fill="#475569" fontSize="10">
                {value.toFixed(precision)} {metric.unit}
              </text>
            </g>
          );
        })}
        <polyline fill="none" stroke={metric.color} strokeWidth="2.4" points={points.join(" ")} />
        <text x={width - padX - 2} y={padY + 12} textAnchor="end" fill="#334155" fontSize="11" fontWeight="700">
          Unit: {metric.unit}
        </text>
      </svg>
      <p className="chart-caption">
        Live {metric.label} feed ({metric.unit})
      </p>
    </div>
  );
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [loginForm, setLoginForm] = useState({ email: "", password: "" });
  const [registerForm, setRegisterForm] = useState({
    full_name: "",
    email: "",
    password: "",
    age: "",
    gender: "",
    blood_group: "",
    medical_history: "",
    phone: "",
    address: "",
    emergency_contact_name: "",
    emergency_contact_phone: "",
  });

  async function onLogin(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const payload = await patientLogin(loginForm);
      onAuthenticated(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function onRegister(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const payload = await patientRegister({
        ...registerForm,
        age: registerForm.age ? Number(registerForm.age) : null,
      });
      onAuthenticated(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <h1>Patient Portal</h1>
        <p>Create your account, request doctors, and monitor your real-time vitals.</p>

        <div className="auth-tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            Login
          </button>
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            Create Account
          </button>
        </div>

        {error ? <div className="error">{error}</div> : null}

        {mode === "login" ? (
          <form className="form-grid" onSubmit={onLogin}>
            <input
              placeholder="Email"
              type="email"
              value={loginForm.email}
              onChange={(event) => setLoginForm((prev) => ({ ...prev, email: event.target.value }))}
              required
            />
            <input
              placeholder="Password"
              type="password"
              value={loginForm.password}
              onChange={(event) => setLoginForm((prev) => ({ ...prev, password: event.target.value }))}
              required
            />
            <button disabled={loading}>{loading ? "Signing in..." : "Sign In"}</button>
          </form>
        ) : (
          <form className="form-grid" onSubmit={onRegister}>
            <input
              placeholder="Full Name"
              value={registerForm.full_name}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, full_name: event.target.value }))}
              required
            />
            <input
              placeholder="Email"
              type="email"
              value={registerForm.email}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, email: event.target.value }))}
              required
            />
            <input
              placeholder="Password (min 6 chars)"
              type="password"
              value={registerForm.password}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, password: event.target.value }))}
              required
            />
            <input
              placeholder="Phone"
              value={registerForm.phone}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, phone: event.target.value }))}
              required
            />
            <input
              placeholder="Age (optional)"
              type="number"
              value={registerForm.age}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, age: event.target.value }))}
            />
            <input
              placeholder="Gender (optional)"
              value={registerForm.gender}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, gender: event.target.value }))}
            />
            <input
              placeholder="Blood Group (optional)"
              value={registerForm.blood_group}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, blood_group: event.target.value }))}
            />
            <input
              placeholder="Address (optional)"
              value={registerForm.address}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, address: event.target.value }))}
            />
            <input
              placeholder="Emergency Contact Name (optional)"
              value={registerForm.emergency_contact_name}
              onChange={(event) =>
                setRegisterForm((prev) => ({ ...prev, emergency_contact_name: event.target.value }))
              }
            />
            <input
              placeholder="Emergency Contact Phone (optional)"
              value={registerForm.emergency_contact_phone}
              onChange={(event) =>
                setRegisterForm((prev) => ({ ...prev, emergency_contact_phone: event.target.value }))
              }
            />
            <textarea
              placeholder="Medical history / notes (optional)"
              value={registerForm.medical_history}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, medical_history: event.target.value }))}
            />
            <button disabled={loading}>{loading ? "Creating..." : "Create Patient Account"}</button>
          </form>
        )}
      </section>
    </main>
  );
}

function Dashboard({ auth, onLogout }) {
  const token = auth.access_token;
  const [profile, setProfile] = useState(auth.user);
  const [error, setError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [doctorResults, setDoctorResults] = useState([]);
  const [requests, setRequests] = useState([]);
  const [acceptedDoctors, setAcceptedDoctors] = useState([]);
  const [vitals, setVitals] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [selectedDoctorUid, setSelectedDoctorUid] = useState("");
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [metricKey, setMetricKey] = useState("heart_rate");
  const [showAllAlerts, setShowAllAlerts] = useState(false);

  const currentVitals = latest(vitals);
  const acceptedDoctorIds = useMemo(
    () => new Set(acceptedDoctors.map((doctor) => doctor.doctor_uid)),
    [acceptedDoctors]
  );

  const visibleSearchResults = useMemo(
    () => doctorResults.filter((doctor) => !acceptedDoctorIds.has(doctor.doctor_uid)),
    [doctorResults, acceptedDoctorIds]
  );

  const selectedDoctor = useMemo(
    () => acceptedDoctors.find((item) => item.doctor_uid === selectedDoctorUid) || null,
    [acceptedDoctors, selectedDoctorUid]
  );
  const alertSummary = useMemo(() => {
    const summary = { critical: 0, moderate: 0, stable: 0 };
    alerts.forEach((alert) => {
      if (alert.severity === "high") summary.critical += 1;
      else if (alert.severity === "medium") summary.moderate += 1;
      else summary.stable += 1;
    });
    return summary;
  }, [alerts]);
  const visibleAlerts = useMemo(() => (showAllAlerts ? alerts : alerts.slice(0, 5)), [alerts, showAllAlerts]);

  async function loadBaseData() {
    const [profileData, requestsData, acceptedDoctorsData, vitalsData, alertsData] = await Promise.all([
      getPatientProfile(token),
      getDoctorRequests(token),
      getAcceptedDoctors(token),
      getVitals(token),
      getAlerts(token),
    ]);

    setProfile(profileData);
    setRequests(requestsData);
    setAcceptedDoctors(acceptedDoctorsData);
    setVitals(vitalsData);
    setAlerts(alertsData);
    if (!selectedDoctorUid && acceptedDoctorsData.length) {
      setSelectedDoctorUid(acceptedDoctorsData[0].doctor_uid);
    }
  }

  async function loadMessagesForDoctor(doctorUid) {
    if (!doctorUid) {
      setMessages([]);
      return;
    }
    const data = await getMessages(token, doctorUid);
    setMessages(data);
  }

  useEffect(() => {
    loadBaseData().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    loadMessagesForDoctor(selectedDoctorUid).catch((err) => setError(err.message));
  }, [selectedDoctorUid]);

  useEffect(() => {
    const socket = openPatientSocket(token, (payload) => {
      if (payload.type === "vital_update") {
        setVitals((prev) => [...prev, payload.data].slice(-MAX_VITALS));
      }
      if (payload.type === "alert") {
        setAlerts((prev) => [payload.data, ...prev].slice(0, MAX_VITALS));
      }
      if (payload.type === "doctor_request_update") {
        setRequests((prev) =>
          uniqueById([payload.data, ...prev.filter((item) => item.id !== payload.data.id)]).sort(
            (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
          )
        );
        if (payload.data.status === "accepted") {
          getAcceptedDoctors(token).then(setAcceptedDoctors).catch(() => {});
        }
      }
      if (payload.type === "message") {
        const message = payload.data;
        if (message.doctor_uid === selectedDoctorUid) {
          setMessages((prev) => uniqueById([...prev, message]));
        }
      }
    });

    const ping = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("ping");
      }
    }, 20000);

    return () => {
      clearInterval(ping);
      socket.close();
    };
  }, [token, selectedDoctorUid]);

  async function runDoctorSearch() {
    try {
      setError("");
      const data = await searchDoctors(token, searchTerm);
      setDoctorResults(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function requestDoctor(doctorUid) {
    try {
      setError("");
      await sendDoctorRequest(token, doctorUid);
      const [requestsData, acceptedDoctorsData] = await Promise.all([
        getDoctorRequests(token),
        getAcceptedDoctors(token),
      ]);
      setRequests(requestsData);
      setAcceptedDoctors(acceptedDoctorsData);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSendMessage(event) {
    event.preventDefault();
    if (!selectedDoctorUid || !draft.trim()) return;
    try {
      await sendMessage(token, selectedDoctorUid, draft.trim());
      setDraft("");
      const data = await getMessages(token, selectedDoctorUid);
      setMessages(data);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <div>
          <h1>Patient Workspace</h1>
          <p>
            {profile.full_name} | {profile.patient_uid}
          </p>
        </div>
        <button
          onClick={() => {
            clearAuth();
            onLogout();
          }}
        >
          Logout
        </button>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="panel-grid two">
        <article className="card">
          <h2>Profile & Care Team</h2>
          <div className="profile-list">
            <p>Email: {profile.email}</p>
            <p>Phone: {profile.phone}</p>
            <p>Blood Group: {profile.blood_group || "Not provided"}</p>
            <p>Emergency Contact: {profile.emergency_contact_name || "Not provided"}</p>
          </div>
          <h3>Accepted Doctors</h3>
          <div className="care-team-list">
            {acceptedDoctors.length === 0 ? (
              <p className="muted">No accepted doctors yet.</p>
            ) : (
              acceptedDoctors.map((doctor) => (
                <div key={doctor.doctor_uid} className="doctor-chip accepted">
                  <strong>{doctor.full_name}</strong>
                  <span>
                    {doctor.doctor_uid} | {doctor.department || "General"}
                  </span>
                </div>
              ))
            )}
          </div>
        </article>

        <article className="card">
          <h2>Find & Request Doctor</h2>
          <div className="inline">
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search by doctor name or ID"
            />
            <button onClick={runDoctorSearch}>Search</button>
          </div>
          <p className="muted tiny">Accepted doctors are hidden from this search list.</p>
          <div className="doctor-result-list">
            {visibleSearchResults.length === 0 ? (
              <p className="muted">No new doctors found for this query.</p>
            ) : (
              visibleSearchResults.map((doctor) => (
                <div key={doctor.doctor_uid} className="doctor-result">
                  <div>
                    <strong>{doctor.full_name}</strong>
                    <p>
                      {doctor.doctor_uid} | {doctor.department || "General"} |{" "}
                      {doctor.qualification || "Qualification not added"}
                    </p>
                  </div>
                  <button onClick={() => requestDoctor(doctor.doctor_uid)}>Request</button>
                </div>
              ))
            )}
          </div>
        </article>
      </section>

      <section className="panel-grid two">
        <article className="card">
          <h2>Doctor Request Status</h2>
          <div className="request-list">
            {requests.length === 0 ? (
              <p className="muted">No requests yet.</p>
            ) : (
              requests.map((item) => (
                <div key={item.id} className="request-row">
                  <div>
                    <strong>
                      {item.doctor.full_name} ({item.doctor.doctor_uid})
                    </strong>
                    <p>{item.doctor.department || "General"}</p>
                  </div>
                  <span className={`status-pill ${item.status}`}>{item.status.toUpperCase()}</span>
                </div>
              ))
            )}
          </div>
        </article>

        <article className="card">
          <h2>Emergency Alerts</h2>
          <div className="alert-summary-row">
            <span className="alert-counter critical">Critical: {alertSummary.critical}</span>
            <span className="alert-counter moderate">Moderate: {alertSummary.moderate}</span>
            <span className="alert-counter stable">Stable: {alertSummary.stable}</span>
          </div>
          <div className="alert-stack">
            {alerts.length === 0 ? (
              <p className="muted">No alerts yet.</p>
            ) : (
              visibleAlerts.map((alert) => (
                <div key={alert.id} className={`alert-card ${severityClass(alert.severity)}`}>
                  <strong>
                    {alert.severity.toUpperCase()} | {fmt(alert.created_at)}
                  </strong>
                  <p className="alert-message">{alert.message}</p>
                </div>
              ))
            )}
          </div>
          {alerts.length > 5 ? (
            <button className="ghost-inline" onClick={() => setShowAllAlerts((prev) => !prev)}>
              {showAllAlerts ? "Show less alerts" : `Show all alerts (${alerts.length})`}
            </button>
          ) : null}
        </article>
      </section>

      <section className="card">
        <h2>Live Vitals Feed</h2>
        <div className="metric-tabs">
          {METRICS.map((metric) => (
            <button
              key={metric.key}
              className={`metric-btn ${metricKey === metric.key ? "active" : ""}`}
              onClick={() => setMetricKey(metric.key)}
            >
              {metric.label}
            </button>
          ))}
        </div>

        <MedicalVitalChart vitals={vitals} metricKey={metricKey} />

        <div className="vital-summary">
          <div>
            <label>Heart Rate</label>
            <p>{currentVitals ? `${currentVitals.heart_rate} bpm` : "--"}</p>
          </div>
          <div>
            <label>SpO2</label>
            <p>{currentVitals ? `${currentVitals.spo2}%` : "--"}</p>
          </div>
          <div>
            <label>Temperature</label>
            <p>{currentVitals ? `${currentVitals.temperature_c} C` : "--"}</p>
          </div>
          <div>
            <label>Blood Pressure</label>
            <p>{currentVitals ? `${currentVitals.systolic_bp}/${currentVitals.diastolic_bp}` : "--"}</p>
          </div>
          <div>
            <label>Respiratory</label>
            <p>{currentVitals ? `${currentVitals.respiratory_rate} rpm` : "--"}</p>
          </div>
        </div>
      </section>

      <section className="card">
        <h2>Message Doctor</h2>
        <div className="inline">
          <select value={selectedDoctorUid} onChange={(event) => setSelectedDoctorUid(event.target.value)}>
            <option value="">Select accepted doctor</option>
            {acceptedDoctors.map((doctor) => (
              <option key={doctor.doctor_uid} value={doctor.doctor_uid}>
                {doctor.full_name} ({doctor.doctor_uid})
              </option>
            ))}
          </select>
          {selectedDoctor ? <span className="muted">{selectedDoctor.department || "General"}</span> : null}
        </div>

        <div className="chat-scroll">
          {messages.length === 0 ? (
            <p className="muted">No messages yet.</p>
          ) : (
            messages.map((message) => (
              <div key={message.id} className={`bubble ${message.sender_role === "patient" ? "self" : "other"}`}>
                <p>{message.content}</p>
                <span>{fmt(message.created_at)}</span>
              </div>
            ))
          )}
        </div>

        <form className="compose-row" onSubmit={handleSendMessage}>
          <input
            placeholder="Type your message"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={!selectedDoctorUid}
          />
          <button disabled={!selectedDoctorUid || !draft.trim()}>Send</button>
        </form>
      </section>
    </main>
  );
}

export default function App() {
  const [auth, setAuth] = useState(getStoredAuth());

  function handleAuthenticated(payload) {
    saveAuth(payload);
    setAuth(payload);
  }

  if (!auth?.access_token) {
    return <AuthScreen onAuthenticated={handleAuthenticated} />;
  }

  return <Dashboard auth={auth} onLogout={() => setAuth(null)} />;
}
