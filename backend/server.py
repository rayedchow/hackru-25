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
import json
import string
import random
from io import BytesIO
from pathlib import Path
from cron_server.synthesis import ask
from detection.scroll import detect_scroll
from detection.app import detect_app
from dashboard import HTML
import ws_manager
from cron_server.datasetup import graph_driver, gemini_model

# Cropping configuration (in pixels) for dashboard display
# Adjust these values to control how much to crop from each side
CROP_TOP = 100  # pixels to crop from top
CROP_BOTTOM = 300  # pixels to crop from bottom
CROP_LEFT = 0  # pixels to crop from left
CROP_RIGHT = 110  # pixels to crop from right

# Setup
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
logging.getLogger("PIL").setLevel(logging.INFO)  # Silence PIL debug logs
logging.getLogger("numba").setLevel(logging.WARNING)  # Silence numba debug logs
logger = logging.getLogger("brainrot")

# Content queue database path
CONTENT_QUEUE_PATH = Path(__file__).parent / "database" / "content_queue.json"

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
    "content_id": None,
}


def generate_content_id() -> str:
    """Generate a random 10-character content ID."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=10))


def save_to_content_queue(image_b64: str, content_id: str):
    """Save content data to content_queue.json."""
    try:
        # Load existing queue
        if CONTENT_QUEUE_PATH.exists():
            with open(CONTENT_QUEUE_PATH, "r") as f:
                queue = json.load(f)
        else:
            queue = []

        # Add new entry
        entry = {
            "image": image_b64,
            "content_id": content_id,
            "timestamp": time.time(),
        }
        queue.append(entry)

        # Save back to file
        with open(CONTENT_QUEUE_PATH, "w") as f:
            json.dump(queue, f, indent=2)

    except Exception as e:
        logger.error(f"Failed to save to content queue: {e}")


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

    # Only process video frames
    if upload_type != "video":
        return JSONResponse({"ok": True})

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
        session["content_id"] = generate_content_id()
        logger.info(f"📱 New session started: {session['id'][:8]}")
        logger.info(f"🆔 Initial content ID: {session['content_id']}")

    session["frame_count"] += 1
    now = time.time()

    # Detect which app is being viewed (using FULL image)
    app_name = detect_app(image)

    # Detect scroll with debouncing (using FULL image)
    did_scroll = False
    scroll_detected, current_hash = detect_scroll(image, session["last_hash"])

    # Debug: Calculate hamming distance for logging
    if session["last_hash"] is not None:
        from detection.scroll import hamming_distance

        distance = hamming_distance(session["last_hash"], current_hash)
        logger.debug(f"Frame difference: {distance} bits")

    session["last_hash"] = current_hash

    # Apply debounce (prevent rapid scroll detections)
    if scroll_detected and (now - session["last_scroll_time"]) >= 2.5:
        did_scroll = True
        session["last_scroll_time"] = now
        # Generate new content ID on scroll
        session["content_id"] = generate_content_id()
        logger.info(f"🔄 Scroll detected (frame {session['frame_count']})")
        logger.info(f"🆔 New content ID: {session['content_id']}")

    # Crop image for dashboard display
    width, height = image.size
    crop_box = (
        CROP_LEFT,  # left
        CROP_TOP,  # top
        width - CROP_RIGHT,  # right
        height - CROP_BOTTOM,  # bottom
    )
    cropped_image = image.crop(crop_box)

    # Encode cropped image to base64
    buffered = BytesIO()
    cropped_image.save(buffered, format="JPEG", quality=85)
    cropped_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    # Save to content queue
    save_to_content_queue(cropped_b64, session["content_id"])

    # Broadcast to dashboard (with CROPPED image for display)
    await ws_manager.broadcast(
        {
            "type": "frame",
            "session_id": session["id"],
            "frame_number": session["frame_count"],
            "app": app_name,
            "did_scroll": did_scroll,
            "image": cropped_b64,
        }
    )

    # Log frame
    scroll_marker = "🔄" if did_scroll else "  "
    logger.info(f"{scroll_marker} Frame {session['frame_count']:04d} | {app_name}")

    return JSONResponse({"ok": True})


@app.get("/graph")
def fetch_graph_general():
    """
    Pull a general subgraph from Neo4j and return Cytoscape/ForceGraph-friendly data.

    Args:
        path_limit: how many paths to sample from the graph (affects size).
        include_node_labels: if provided, only include nodes having ANY of these labels.
        include_rel_types: if provided, only include relationships whose type is in this list.

    Returns:
        dict with 'nodes' and 'edges' arrays:
          nodes: [{ data: { id, label, ...props } }, ...]
          edges: [{ data: { id, source, target, type, ...props } }, ...]
        (You can easily transform for react-force-graph by mapping data fields.)
    """
    # Default filters to empty lists for Cypher parameter handling
    include_node_labels = []
    include_rel_types = []
    path_limit = 1000

    cypher = """
    // Sample a bunch of paths
    MATCH p = (a)-[r]->(b)
    WHERE (
      size($nodeLabels) = 0 OR
      any(l IN labels(a) WHERE l IN $nodeLabels) OR
      any(l IN labels(b) WHERE l IN $nodeLabels)
    )
    AND (
      size($relTypes) = 0 OR type(r) IN $relTypes
    )
    WITH r, nodes(p) AS ns
    LIMIT $pathLimit

    // Collect distinct rels and nodes without APOC
    WITH collect(DISTINCT r) AS rels, collect(DISTINCT ns) AS nlists
    UNWIND nlists AS ns
    UNWIND ns AS n
    WITH rels, collect(DISTINCT n) AS nodes
    RETURN nodes, rels
    """

    with graph_driver.session() as s:
        rec = s.run(
            cypher,
            pathLimit=path_limit,
            nodeLabels=include_node_labels,
            relTypes=include_rel_types,
        ).single()

    if not rec:
        return {"nodes": [], "edges": []}

    neo_nodes = rec["nodes"] or []
    neo_rels = rec["rels"] or []

    # Cytoscape elements (you can tweak fields as you like)
    nodes = [
        {
            "data": {
                "id": n.id if hasattr(n, "id") else n.identity,  # neo4j>=5 uses .id
                "label": (n.labels and list(n.labels)[0]) or "Node",
                **n._properties,
            }
        }
        for n in neo_nodes
    ]

    edges = [
        {
            "data": {
                "id": r.id if hasattr(r, "id") else r.identity,
                "source": r.start_node.id if hasattr(r.start_node, "id") else r.start,
                "target": r.end_node.id if hasattr(r.end_node, "id") else r.end,
                "type": r.type,
                **r._properties,
            }
        }
        for r in neo_rels
    ]

    # Ensure all ids are strings (many front-ends expect string ids)
    for e in nodes:
        e["data"]["id"] = str(e["data"]["id"])
    for e in edges:
        e["data"]["id"] = str(e["data"]["id"])
        e["data"]["source"] = str(e["data"]["source"])
        e["data"]["target"] = str(e["data"]["target"])

    return {"nodes": nodes, "edges": edges}


@app.post("/ask_screenshot")
async def ask_screenshot(req: Request):
    data = await req.json()
    image = data.get("screenshot")
    pil_image = Image.open(BytesIO(base64.b64decode(image)))
    question = (
        gemini_model.generate_content(
            [
                "You are an image translator. Output what the image is asking as a question. I will interpret the question and create a response. JUST OUTPUT THE QUESTION IN A QUESTION FORMAT AND GET THE MOST DETAIL OUT OF THE IMAGE INTO THE QUESTION AS POSSIBLE.",
                pil_image,
            ]
        ).text
        or ""
    ).strip()
    print(f"[ask_screenshot] Extracted question: {question}")
    answer = ask(question)
    return {"status": "received", "result": answer}


@app.post("/ask_question")
async def ask_question(req: Request):
    data = await req.json()
    question = data.get("question")
    answer = ask(question)
    return {"status": "received", "result": answer}


if __name__ == "__main__":
    import socket

    ip = socket.gethostbyname(socket.gethostname())

    logger.info("\n" + "=" * 60)
    logger.info("🧠 BrainRot Monitor")
    logger.info(f"Dashboard:  http://{ip}:8000")
    logger.info(f"Upload URL: http://{ip}:8000/upload")
    logger.info("=" * 60 + "\n")

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
