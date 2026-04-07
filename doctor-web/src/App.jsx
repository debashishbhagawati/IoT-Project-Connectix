import { useEffect, useMemo, useState } from "react";
import {
  ackAlert,
  decideRequest,
  doctorLogin,
  doctorRegister,
  getDoctorProfile,
  getEmergencyAlerts,
  getIncomingRequests,
  getMessages,
  getPatientContact,
  getPatientVitals,
  getPatients,
  openDoctorSocket,
  sendMessage,
} from "./api";

const AUTH_KEY = "doctor_portal_auth";
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

function uniqueById(rows) {
  const seen = new Set();
  return rows.filter((row) => {
    if (seen.has(row.id)) return false;
    seen.add(row.id);
    return true;
  });
}

function severityScore(severity) {
  if (severity === "high") return 3;
  if (severity === "medium") return 2;
  return 1;
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
          <pattern id="dr-grid-small" width="12" height="12" patternUnits="userSpaceOnUse">
            <path d="M 12 0 L 0 0 0 12" fill="none" stroke="#dce6f4" strokeWidth="1" />
          </pattern>
          <pattern id="dr-grid-big" width="60" height="60" patternUnits="userSpaceOnUse">
            <rect width="60" height="60" fill="url(#dr-grid-small)" />
            <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#bfd0e8" strokeWidth="1.2" />
          </pattern>
        </defs>
        <rect x="0" y="0" width={width} height={height} fill="url(#dr-grid-big)" rx="10" />
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

function buildTriage(alerts) {
  const grouped = new Map();

  alerts.forEach((alert) => {
    const key = alert.patient_uid;
    const existing = grouped.get(key);
    const score = severityScore(alert.severity);
    const alertTime = new Date(alert.created_at).getTime();

    if (!existing) {
      grouped.set(key, {
        patient_uid: alert.patient_uid,
        patient_name: alert.patient_name,
        latest_alert: alert,
        latest_time: alertTime,
        max_score: score,
        count: 1,
      });
      return;
    }

    existing.count += 1;
    if (score > existing.max_score || (score === existing.max_score && alertTime > existing.latest_time)) {
      existing.max_score = score;
      existing.latest_alert = alert;
      existing.latest_time = alertTime;
    }
  });

  const cards = [...grouped.values()].sort((a, b) => b.latest_time - a.latest_time);
  return {
    critical: cards.filter((item) => item.max_score >= 3),
    moderate: cards.filter((item) => item.max_score < 3),
  };
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [loginForm, setLoginForm] = useState({ email: "", password: "" });
  const [registerForm, setRegisterForm] = useState({
    full_name: "",
    email: "",
    password: "",
    qualification: "",
    department: "",
    experience_years: "",
    expertises: "",
    phone: "",
  });

  async function onLogin(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const payload = await doctorLogin(loginForm);
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
      const payload = await doctorRegister({
        ...registerForm,
        experience_years: registerForm.experience_years ? Number(registerForm.experience_years) : null,
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
        <h1>Doctor Portal</h1>
        <p>Review patient requests, triage emergencies, and coordinate via chat.</p>

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
          <form className="form-grid form-grid--login" onSubmit={onLogin}>
            <input
              type="email"
              placeholder="Email"
              value={loginForm.email}
              onChange={(event) => setLoginForm((prev) => ({ ...prev, email: event.target.value }))}
              required
            />
            <input
              type="password"
              placeholder="Password"
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
              type="email"
              placeholder="Email"
              value={registerForm.email}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, email: event.target.value }))}
              required
            />
            <input
              type="password"
              placeholder="Password (min 6 chars)"
              value={registerForm.password}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, password: event.target.value }))}
              required
            />
            <input
              placeholder="Qualification"
              value={registerForm.qualification}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, qualification: event.target.value }))}
            />
            <input
              placeholder="Department (optional)"
              value={registerForm.department}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, department: event.target.value }))}
            />
            <input
              type="number"
              placeholder="Experience in years (optional)"
              value={registerForm.experience_years}
              onChange={(event) =>
                setRegisterForm((prev) => ({ ...prev, experience_years: event.target.value }))
              }
            />
            <input
              placeholder="Expertises (optional)"
              value={registerForm.expertises}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, expertises: event.target.value }))}
            />
            <input
              placeholder="Phone (optional)"
              value={registerForm.phone}
              onChange={(event) => setRegisterForm((prev) => ({ ...prev, phone: event.target.value }))}
            />
            <button disabled={loading}>{loading ? "Creating..." : "Create Doctor Account"}</button>
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
  const [workspaceTab, setWorkspaceTab] = useState("operations");
  const [requestStatus, setRequestStatus] = useState("pending");
  const [requests, setRequests] = useState([]);
  const [patients, setPatients] = useState([]);
  const [sort, setSort] = useState("asc");
  const [search, setSearch] = useState("");
  const [selectedPatientUid, setSelectedPatientUid] = useState("");
  const [vitals, setVitals] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [patientContact, setPatientContact] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [metricKey, setMetricKey] = useState("heart_rate");
  const [selectedAlert, setSelectedAlert] = useState(null);

  const selectedPatient = useMemo(
    () => patients.find((patient) => patient.patient_uid === selectedPatientUid) || null,
    [patients, selectedPatientUid]
  );

  const triage = useMemo(() => buildTriage(alerts), [alerts]);

  async function loadMainData() {
    const [doctorProfile, requestRows, patientRows, alertRows] = await Promise.all([
      getDoctorProfile(token),
      getIncomingRequests(token, requestStatus),
      getPatients(token, sort, search),
      getEmergencyAlerts(token, false),
    ]);
    setProfile(doctorProfile);
    setRequests(requestRows);
    setPatients(patientRows);
    setAlerts(alertRows);
    if (!selectedPatientUid && patientRows.length) {
      setSelectedPatientUid(patientRows[0].patient_uid);
    }
  }

  async function loadSelectedPatientData(patientUid) {
    if (!patientUid) {
      setVitals([]);
      setMessages([]);
      setPatientContact(null);
      return;
    }
    const [vitalsData, messagesData, contactData] = await Promise.all([
      getPatientVitals(token, patientUid),
      getMessages(token, patientUid),
      getPatientContact(token, patientUid),
    ]);
    setVitals(vitalsData);
    setMessages(messagesData);
    setPatientContact(contactData);
  }

  useEffect(() => {
    loadMainData().catch((err) => setError(err.message));
  }, [requestStatus, sort, search]);

  useEffect(() => {
    loadSelectedPatientData(selectedPatientUid).catch((err) => setError(err.message));
  }, [selectedPatientUid]);

  useEffect(() => {
    const socket = openDoctorSocket(token, (payload) => {
      if (payload.type === "doctor_request") {
        if (requestStatus === "pending") {
          setRequests((prev) => uniqueById([payload.data, ...prev]));
        }
      }
      if (payload.type === "vital_update" && payload.data.patient_uid === selectedPatientUid) {
        setVitals((prev) => [...prev, payload.data].slice(-150));
      }
      if (payload.type === "alert") {
        setAlerts((prev) => uniqueById([payload.data, ...prev]).slice(0, 200));
      }
      if (payload.type === "message" && payload.data.patient_uid === selectedPatientUid) {
        setMessages((prev) => uniqueById([...prev, payload.data]));
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
  }, [token, selectedPatientUid, requestStatus]);

  async function reviewRequest(requestId, action) {
    try {
      await decideRequest(token, requestId, action);
      const [requestRows, patientRows] = await Promise.all([
        getIncomingRequests(token, requestStatus),
        getPatients(token, sort, search),
      ]);
      setRequests(requestRows);
      setPatients(patientRows);
      if (!selectedPatientUid && patientRows.length) {
        setSelectedPatientUid(patientRows[0].patient_uid);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function openTriagePatient(card) {
    setSelectedAlert(card.latest_alert);
    setWorkspaceTab("operations");
    setSelectedPatientUid(card.patient_uid);
  }

  async function acknowledge(alertId) {
    try {
      await ackAlert(token, alertId);
      const refreshed = await getEmergencyAlerts(token, false);
      setAlerts(refreshed);
      if (selectedAlert && selectedAlert.id === alertId) {
        setSelectedAlert(null);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function onSendMessage(event) {
    event.preventDefault();
    if (!selectedPatientUid || !draft.trim()) return;
    try {
      await sendMessage(token, selectedPatientUid, draft.trim());
      setDraft("");
      const data = await getMessages(token, selectedPatientUid);
      setMessages(data);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <div>
          <h1>Doctor Workspace</h1>
          <p>
            {profile.full_name} ({profile.doctor_uid}) | {profile.department || "General"}
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

      <nav className="workspace-tabs">
        <button
          className={workspaceTab === "operations" ? "active" : ""}
          onClick={() => setWorkspaceTab("operations")}
        >
          Care Operations
        </button>
        <button className={workspaceTab === "messages" ? "active" : ""} onClick={() => setWorkspaceTab("messages")}>
          Messages
        </button>
      </nav>

      {error ? <div className="error">{error}</div> : null}

      {workspaceTab === "operations" ? (
        <>
          <section className="panel-grid two">
            <article className="card">
              <h2>Incoming Patient Requests</h2>
              <div className="inline">
                <select value={requestStatus} onChange={(event) => setRequestStatus(event.target.value)}>
                  <option value="pending">Pending</option>
                  <option value="accepted">Accepted</option>
                  <option value="rejected">Rejected</option>
                  <option value="all">All</option>
                </select>
              </div>
              <div className="request-list">
                {requests.length === 0 ? (
                  <p className="muted">No requests in this state.</p>
                ) : (
                  requests.map((request) => (
                    <div key={request.id} className="request-row">
                      <div>
                        <strong>
                          {request.patient.full_name} ({request.patient.patient_uid})
                        </strong>
                        <p>
                          Phone: {request.patient.phone} | Blood Group: {request.patient.blood_group || "N/A"}
                        </p>
                        <p>Status: {request.status.toUpperCase()}</p>
                      </div>
                      {request.status === "pending" ? (
                        <div className="btn-group">
                          <button onClick={() => reviewRequest(request.id, "accept")}>Accept</button>
                          <button className="ghost" onClick={() => reviewRequest(request.id, "reject")}>
                            Reject
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
            </article>

            <article className="card">
              <h2>Emergency Triage</h2>
              <div className="triage-block">
                <h3>Critical Patients (Emergency)</h3>
                <div className="triage-list">
                  {triage.critical.length === 0 ? (
                    <p className="muted">No critical patients right now.</p>
                  ) : (
                    triage.critical.map((card) => (
                      <div key={card.patient_uid} className="triage-card critical">
                        <button className="triage-main" onClick={() => openTriagePatient(card)}>
                          <strong>
                            {card.patient_name} ({card.patient_uid})
                          </strong>
                          <p>{card.latest_alert.message}</p>
                          <span>
                            Last: {fmt(card.latest_alert.created_at)} | Pending alerts: {card.count}
                          </span>
                        </button>
                        <button className="ghost" onClick={() => acknowledge(card.latest_alert.id)}>
                          Ack Latest
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="triage-block">
                <h3>Moderate (Review Needed)</h3>
                <div className="triage-list">
                  {triage.moderate.length === 0 ? (
                    <p className="muted">No moderate alerts right now.</p>
                  ) : (
                    triage.moderate.map((card) => (
                      <div key={card.patient_uid} className="triage-card moderate">
                        <button className="triage-main" onClick={() => openTriagePatient(card)}>
                          <strong>
                            {card.patient_name} ({card.patient_uid})
                          </strong>
                          <p>{card.latest_alert.message}</p>
                          <span>
                            Last: {fmt(card.latest_alert.created_at)} | Pending alerts: {card.count}
                          </span>
                        </button>
                        <button className="ghost" onClick={() => acknowledge(card.latest_alert.id)}>
                          Ack Latest
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </article>
          </section>

          <section className="panel-grid two">
            <article className="card">
              <h2>Patients Under You</h2>
              <div className="inline">
                <input
                  placeholder="Search by patient ID"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                <select value={sort} onChange={(event) => setSort(event.target.value)}>
                  <option value="asc">ID Asc</option>
                  <option value="desc">ID Desc</option>
                </select>
              </div>

              <div className="patient-list">
                {patients.length === 0 ? (
                  <p className="muted">No accepted patients yet.</p>
                ) : (
                  patients.map((patient) => (
                    <button
                      key={patient.patient_uid}
                      className={`patient-row ${patient.patient_uid === selectedPatientUid ? "active" : ""}`}
                      onClick={() => setSelectedPatientUid(patient.patient_uid)}
                    >
                      <span>{patient.patient_uid}</span>
                      <span>{patient.full_name}</span>
                    </button>
                  ))
                )}
              </div>
            </article>

            <article className="card">
              <h2>
                Patient Report {selectedPatient ? `| ${selectedPatient.full_name} (${selectedPatient.patient_uid})` : ""}
              </h2>
              {selectedAlert ? (
                <p className={`selected-alert ${severityScore(selectedAlert.severity) >= 3 ? "critical" : "moderate"}`}>
                  Selected alert: {selectedAlert.severity.toUpperCase()} | {selectedAlert.message}
                </p>
              ) : null}

              {patientContact ? (
                <div className="contact-card">
                  <h3>Contact Details</h3>
                  <p>Phone: {patientContact.phone}</p>
                  <p>Address: {patientContact.address || "Not provided"}</p>
                  <p>Emergency Contact: {patientContact.emergency_contact_name || "N/A"}</p>
                  <p>Emergency Phone: {patientContact.emergency_contact_phone || "N/A"}</p>
                </div>
              ) : (
                <p className="muted">Select a patient from triage or list to view report.</p>
              )}

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
            </article>
          </section>
        </>
      ) : (
        <section className="card whatsapp-panel">
          <h2>Doctor Messaging Panel</h2>
          <div className="whatsapp-layout">
            <aside className="chat-sidebar">
              <h3>Patients</h3>
              <div className="chat-contact-list">
                {patients.length === 0 ? (
                  <p className="muted">No accepted patients yet.</p>
                ) : (
                  patients.map((patient) => (
                    <button
                      key={patient.patient_uid}
                      className={`chat-contact ${patient.patient_uid === selectedPatientUid ? "active" : ""}`}
                      onClick={() => setSelectedPatientUid(patient.patient_uid)}
                    >
                      <strong>{patient.full_name}</strong>
                      <span>{patient.patient_uid}</span>
                    </button>
                  ))
                )}
              </div>
            </aside>

            <section className="chat-main">
              <header className="chat-main-header">
                {selectedPatient ? (
                  <>
                    <h3>{selectedPatient.full_name}</h3>
                    <p>{selectedPatient.patient_uid}</p>
                  </>
                ) : (
                  <h3>Select a patient to start chat</h3>
                )}
              </header>

              <div className="chat-scroll">
                {messages.length === 0 ? (
                  <p className="muted">No messages yet.</p>
                ) : (
                  messages.map((message) => (
                    <div key={message.id} className={`bubble ${message.sender_role === "doctor" ? "self" : "other"}`}>
                      <p>{message.content}</p>
                      <span>{fmt(message.created_at)}</span>
                    </div>
                  ))
                )}
              </div>

              <form className="compose-row" onSubmit={onSendMessage}>
                <input
                  placeholder="Write a message"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  disabled={!selectedPatientUid}
                />
                <button disabled={!selectedPatientUid || !draft.trim()}>Send</button>
              </form>
            </section>
          </div>
        </section>
      )}
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
