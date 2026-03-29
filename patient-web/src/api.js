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

export function patientRegister(payload) {
  return request("/api/auth/patient/register", { method: "POST", body: payload });
}

export function patientLogin(payload) {
  return request("/api/auth/patient/login", { method: "POST", body: payload });
}

export function getPatientProfile(token) {
  return request("/api/patient/profile", { token });
}

export function searchDoctors(token, q = "") {
  return request(`/api/patient/doctors/search?q=${encodeURIComponent(q)}`, { token });
}

export function sendDoctorRequest(token, doctorUid) {
  return request("/api/patient/doctor-requests", {
    token,
    method: "POST",
    body: { doctor_uid: doctorUid },
  });
}

export function getDoctorRequests(token) {
  return request("/api/patient/doctor-requests", { token });
}

export function getAcceptedDoctors(token) {
  return request("/api/patient/accepted-doctors", { token });
}

export function getVitals(token, limit = 80) {
  return request(`/api/patient/vitals?limit=${limit}`, { token });
}

export function getAlerts(token, limit = 80) {
  return request(`/api/patient/alerts?limit=${limit}`, { token });
}

export function getMessages(token, doctorUid, limit = 120) {
  return request(`/api/patient/messages/${doctorUid}?limit=${limit}`, { token });
}

export function sendMessage(token, doctorUid, content) {
  return request(`/api/patient/messages/${doctorUid}`, {
    token,
    method: "POST",
    body: { content },
  });
}

export function openPatientSocket(token, onMessage) {
  const wsBase = API_BASE.replace("http://", "ws://").replace("https://", "wss://");
  const socket = new WebSocket(`${wsBase}/ws/patient?token=${encodeURIComponent(token)}`);

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

