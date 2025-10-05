"""
BrainRot Monitor - Simple screen recording analyzer.
Detects scrolling behavior on short-form video platforms.
"""

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import uvicorn
import base64
import uuid
import time
import logging
from io import BytesIO

from detection.scroll import detect_scroll
from detection.app import detect_app
from dashboard import HTML
import ws_manager

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("brainrot")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple session state
session = {
    "id": None,
    "frame_count": 0,
    "last_hash": None,
    "last_scroll_time": 0.0,
}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve web dashboard."""
    return HTML


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live updates."""
    await ws_manager.websocket_endpoint(websocket)


@app.post("/upload")
async def upload_frame(req: Request):
    """
    Handle frame upload from iOS app.
    Analyzes frame for app detection and scroll behavior.
    """
    try:
        data = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

    upload_type = data.get("type")

    # Handle audio (just acknowledge and ignore for now)
    if upload_type == "audio":
        return JSONResponse({"ok": True})

    # Only process video frames
    if upload_type != "video":
        return JSONResponse({"ok": False, "error": "unknown type"}, status_code=400)

    # Decode image
    b64_image = data.get("payload")
    if not b64_image:
        return JSONResponse({"ok": False, "error": "no image payload"}, status_code=400)

    try:
        image_bytes = base64.b64decode(b64_image)
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        logger.error(f"Failed to decode image: {e}")
        return JSONResponse({"ok": False, "error": "invalid image"}, status_code=400)

    # Initialize session on first frame
    if not session["id"]:
        session["id"] = str(uuid.uuid4())
        logger.info(f"📱 New session started: {session['id'][:8]}")

    session["frame_count"] += 1
    now = time.time()

    # Detect which app is being viewed
    app_name = detect_app(image)

    # Detect scroll with debouncing
    did_scroll = False
    scroll_detected, current_hash = detect_scroll(image, session["last_hash"])
    session["last_hash"] = current_hash

    # Apply debounce (prevent rapid scroll detections)
    if scroll_detected and (now - session["last_scroll_time"]) >= 2.5:
        did_scroll = True
        session["last_scroll_time"] = now
        logger.info(f"🔄 Scroll detected (frame {session['frame_count']})")

    # Broadcast to dashboard
    await ws_manager.broadcast(
        {
            "type": "frame",
            "session_id": session["id"],
            "frame_number": session["frame_count"],
            "app": app_name,
            "did_scroll": did_scroll,
            "image": b64_image,
        }
    )

    # Log frame
    scroll_marker = "🔄" if did_scroll else "  "
    logger.info(f"{scroll_marker} Frame {session['frame_count']:04d} | {app_name}")

    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import socket

    ip = socket.gethostbyname(socket.gethostname())

    logger.info("\n" + "=" * 60)
    logger.info("🧠 BrainRot Monitor")
    logger.info(f"Dashboard:  http://{ip}:8000")
    logger.info(f"Upload URL: http://{ip}:8000/upload")
    logger.info("=" * 60 + "\n")

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
