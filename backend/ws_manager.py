"""
WebSocket management for real-time dashboard updates.
"""

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

# Active WebSocket connections
connections: list[WebSocket] = []
BROADCAST_SEND_TIMEOUT_SECONDS = 0.5


async def websocket_endpoint(websocket: WebSocket) -> None:
    """Handle WebSocket connection lifecycle."""
    await websocket.accept()
    connections.append(websocket)
    try:
        while True:
            # Receiving lets Starlette surface disconnects immediately. Client
            # messages are intentionally ignored; this channel is metadata-only.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in connections:
            connections.remove(websocket)


async def broadcast(message: dict[str, object]) -> None:
    """Send message to all connected WebSocket clients."""

    async def send(ws: WebSocket) -> None:
        try:
            await asyncio.wait_for(
                ws.send_json(message),
                timeout=BROADCAST_SEND_TIMEOUT_SECONDS,
            )
        except Exception:
            if ws in connections:
                connections.remove(ws)

    await asyncio.gather(*(send(ws) for ws in connections[:]))
