from collections import defaultdict
from typing import DefaultDict, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.patient_channels: DefaultDict[str, Set[WebSocket]] = defaultdict(set)
        self.doctor_channels: DefaultDict[str, Set[WebSocket]] = defaultdict(set)

    async def connect_patient(self, patient_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.patient_channels[patient_id].add(websocket)

    async def connect_doctor(self, doctor_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.doctor_channels[doctor_id].add(websocket)

    def disconnect_patient(self, patient_id: str, websocket: WebSocket) -> None:
        self.patient_channels[patient_id].discard(websocket)

    def disconnect_doctor(self, doctor_id: str, websocket: WebSocket) -> None:
        self.doctor_channels[doctor_id].discard(websocket)

    async def broadcast_patient(self, patient_id: str, payload: dict) -> None:
        await self._broadcast_set(self.patient_channels[patient_id], payload)

    async def broadcast_doctor(self, doctor_id: str, payload: dict) -> None:
        await self._broadcast_set(self.doctor_channels[doctor_id], payload)

    async def _broadcast_set(self, sockets: Set[WebSocket], payload: dict) -> None:
        stale = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)

        for socket in stale:
            sockets.discard(socket)
