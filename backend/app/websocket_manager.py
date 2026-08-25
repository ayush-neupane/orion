"""WebSocket connection manager with rooms.

Access model: market tick data is public, so connections are allowed
ANONYMOUSLY (guest). Supplying a valid JWT attaches the authenticated
identity for logging; an invalid supplied token is still rejected.
Other invariants enforced here and in the /ws route:
- Frames larger than settings.max_ws_message_bytes are rejected with
  close code 1009 (message too big) to prevent memory exhaustion.
- Room fan-out is guarded against sending on half-closed sockets.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import jwt as pyjwt
from fastapi import WebSocket

from app.config import get_settings
from app.utils.logger import get_logger

log = get_logger(__name__)
settings = get_settings()


def verify_ws_token(token: str | None) -> dict[str, Any]:
    """Validate the JWT presented at connection upgrade time.

    Anonymous (guest) connections are permitted: an absent token returns
    guest claims, while a SUPPLIED token that is expired/invalid is
    rejected — clients must not send broken credentials.
    """
    if not token:
        return {"sub": "guest", "type": "access"}
    try:
        claims = pyjwt.decode(token, settings.secret_key,
                              algorithms=[settings.algorithm])
    except pyjwt.ExpiredSignatureError as exc:
        raise PermissionError("Token expired") from exc
    except pyjwt.InvalidTokenError as exc:
        raise PermissionError("Invalid token") from exc
    if claims.get("type") != "access":
        raise PermissionError("Invalid token type")
    return claims


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, room: str = "GLOBAL",
                      user: str = "anonymous") -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms.setdefault(room, set()).add(websocket)
        log.info("ws_connected", room=room, user=user)
        await websocket.send_json({"event": "connected", "room": room})

    async def disconnect(self, websocket: WebSocket, room: str) -> None:
        async with self._lock:
            self._rooms.get(room, set()).discard(websocket)

    def move_room(self, websocket: WebSocket, old: str, new: str) -> None:
        # Synchronous membership move; called from the receive loop only.
        self._rooms.get(old, set()).discard(websocket)
        self._rooms.setdefault(new, set()).add(websocket)

    async def broadcast(self, room: str, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._rooms.get(room, set())):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001 - socket already closing
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws, room)

    def room_size(self, room: str) -> int:
        return len(self._rooms.get(room, set()))

    @property
    def active_rooms(self) -> dict[str, int]:
        return {room: len(sockets) for room, sockets in self._rooms.items()
                if sockets}


manager = ConnectionManager()
