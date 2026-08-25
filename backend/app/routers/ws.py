"""Public market WebSocket.

Market tick data is public: upgrade is accepted anonymously (guest) or
with a valid access token (?token=...). A SUPPLIED but invalid/expired
token is refused (close 4001).
Frames > settings.max_ws_message_bytes trigger close 1009.
Clients subscribe to region rooms and receive live tick broadcasts.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.services import universe
from app.websocket_manager import manager, verify_ws_token
from app.utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["ws"])
settings = get_settings()


@router.websocket("/ws/market")
async def ws_market(websocket: WebSocket,
                    token: str = Query(default="")):
    try:
        claims = verify_ws_token(token)
    except PermissionError as exc:
        await websocket.close(code=4001, reason=str(exc))
        return

    room = "GLOBAL"
    await manager.connect(websocket, room=room, user=str(claims.get("sub")))
    try:
        while True:
            message = await websocket.receive_text()
            if len(message.encode("utf-8")) > settings.max_ws_message_bytes:
                await websocket.close(code=1009, reason="Message too large")
                return
            try:
                data = json.loads(message)
                requested = str(data.get("subscribe", "")).upper()[:8]
            except (json.JSONDecodeError, AttributeError):
                continue
            if requested in universe.REGIONS:
                old_room = room
                room = requested
                manager.move_room(websocket, old_room, room)
                await websocket.send_json({"event": "subscribed",
                                           "room": room})
    except WebSocketDisconnect:
        await manager.disconnect(websocket, room)
        log.info("ws_disconnected", room=room)
