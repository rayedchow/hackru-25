"""
WebSocket management for real-time dashboard updates.
"""

from fastapi import WebSocket, WebSocketDisconnect
import asyncio

# Active WebSocket connections
connections: list[WebSocket] = []


async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connection lifecycle."""
    await websocket.accept()
    connections.append(websocket)
    try:
        # Keep connection alive
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in connections:
            connections.remove(websocket)


async def broadcast(message: dict):
    """Send message to all connected WebSocket clients."""
    for ws in connections[:]:
        try:
            await ws.send_json(message)
        except Exception:
            if ws in connections:
                connections.remove(ws)
