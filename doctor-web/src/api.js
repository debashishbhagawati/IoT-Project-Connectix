const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, { method = "GET", token, body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let detail = "Request failed";
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      detail = `${detail} (${response.status})`;
    }
    throw new Error(detail);
  }
  return response.json();
}

export function doctorRegister(payload) {
  return request("/api/auth/doctor/register", { method: "POST", body: payload });
}

export function doctorLogin(payload) {
  return request("/api/auth/doctor/login", { method: "POST", body: payload });
}

export function getDoctorProfile(token) {
  return request("/api/doctor/profile", { token });
}

export function getIncomingRequests(token, status = "pending") {
  return request(`/api/doctor/requests?status=${encodeURIComponent(status)}`, { token });
}

export function decideRequest(token, requestId, action) {
  return request(`/api/doctor/requests/${requestId}/decision`, {
    token,
    method: "POST",
    body: { action },
  });
}

export function getPatients(token, sort = "asc", query = "") {
  return request(`/api/doctor/patients?sort=${sort}&query=${encodeURIComponent(query)}`, { token });
}

export function getPatientVitals(token, patientUid, limit = 100) {
  return request(`/api/doctor/patients/${patientUid}/vitals?limit=${limit}`, { token });
}

export function getEmergencyAlerts(token, includeAcknowledged = false, limit = 100) {
  return request(
    `/api/doctor/emergency-alerts?include_acknowledged=${includeAcknowledged}&limit=${limit}`,
    { token }
  );
}

export function ackAlert(token, alertId) {
  return request(`/api/doctor/emergency-alerts/${alertId}/ack`, { token, method: "POST" });
}

export function getPatientContact(token, patientUid) {
  return request(`/api/doctor/patients/${patientUid}/contact`, { token });
}

export function getMessages(token, patientUid, limit = 120) {
  return request(`/api/doctor/messages/${patientUid}?limit=${limit}`, { token });
}

export function sendMessage(token, patientUid, content) {
  return request(`/api/doctor/messages/${patientUid}`, {
    token,
    method: "POST",
    body: { content },
  });
}

export function openDoctorSocket(token, onMessage) {
  const wsBase = API_BASE.replace("http://", "ws://").replace("https://", "wss://");
  const socket = new WebSocket(`${wsBase}/ws/doctor?token=${encodeURIComponent(token)}`);

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      onMessage(payload);
    } catch (error) {
      console.error("Invalid websocket payload", error);
    }
  };

  return socket;
}

