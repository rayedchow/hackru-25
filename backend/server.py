from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn, base64, os, json, asyncio, uuid, time, re, logging
from datetime import datetime
from io import BytesIO
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("brainrot")

# ── Optional OCR (used for app keywords + like count) ──────────────────────────
try:
    import pytesseract

    OCR = True
except Exception:
    OCR = False
    logger.warning("⚠️  pytesseract not installed – OCR-based detection disabled.")

app = FastAPI()


# Debug middleware to catch all requests
@app.middleware("http")
async def debug_middleware(request: Request, call_next):
    response = await call_next(request)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("captured_frames", exist_ok=True)
os.makedirs("captured_audio", exist_ok=True)
os.makedirs("session_logs", exist_ok=True)

# ── Live session state (in memory, simple by design) ───────────────────────────
active_connections: list[WebSocket] = []
session = {
    "session_id": None,
    "start_time": None,
    "device": None,
    "frames": 0,
    "audio": 0,
    "current_app": "unknown",
    "content_id": None,
    "last_hash": None,  # for pHash scroll
    "last_scroll_ts": 0.0,  # debounce scroll
    "last_like": None,  # normalized int like count
    "last_like_ts": 0.0,  # last time we updated like reading
    "last_confident_app_ts": 0.0,  # last time OCR confidently saw an app
}

# ── Dashboard (minimal UI) ─────────────────────────────────────────────────────
HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>BrainRot</title>
<style>
  body{background:#0e0e0f;color:#e9e9e9;font-family:ui-monospace,monospace;margin:0;padding:16px}
  .row{display:flex;gap:16px;align-items:flex-start}
  .card{background:#161617;border:1px solid #2a2a2c;border-radius:12px;padding:16px}
  #img{max-height:70vh;max-width:50vw;border:1px solid #2a2a2c;border-radius:8px}
  .meta{min-width:360px}
  .kv{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dotted #2a2a2c}
  .kv span:first-child{color:#9aa0a6}
  .badge{display:inline-block;padding:3px 8px;border-radius:999px;font-size:12px;border:1px solid #2a2a2c}
  .ok{color:#00ff88;border-color:#00ff88}
  .warn{color:#ffd400;border-color:#ffd400}
  .app{font-weight:700}
</style>
</head><body>
  <h2>🧠 BrainRot Live</h2>
  <div class="row">
    <img id="img" class="card" alt="No frames yet"/>
    <div class="card meta">
      <div class="kv"><span>Status</span> <span id="status">Waiting…</span></div>
      <div class="kv"><span>Session</span> <span id="sid">—</span></div>
      <div class="kv"><span>Frames</span> <span id="frames">0</span></div>
      <div class="kv"><span>Audio</span> <span id="audio">0</span></div>
      <div class="kv"><span>App</span> <span id="app" class="app">UNKNOWN</span></div>
      <div class="kv"><span>Content ID</span> <span id="cid">—</span></div>
      <div class="kv"><span>Last event</span> <span id="event">—</span></div>
      <div style="margin-top:10px">
        <span id="scrollBadge" class="badge" style="display:none">SCROLL</span>
        <span id="conn" class="badge warn">WebSocket: connecting…</span>
      </div>
    </div>
  </div>
<script>
let ws, frameCount=0, audioCount=0, lastScrollTs=0;
function connect(){
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = ()=>{document.getElementById('conn').textContent='WebSocket: connected';document.getElementById('conn').className='badge ok'};
  ws.onclose= ()=>{document.getElementById('conn').textContent='WebSocket: reconnecting…';document.getElementById('conn').className='badge warn'; setTimeout(connect,1500);};
  ws.onmessage = e=>{
    const d = JSON.parse(e.data);
    if(d.type==='session_start'){
      frameCount=0; audioCount=0;
      document.getElementById('status').textContent='Recording';
      document.getElementById('sid').textContent=d.session_id||'—';
    }
    if(d.type==='session_end'){
      document.getElementById('status').textContent='Stopped';
      document.getElementById('event').textContent='Session ended';
    }
    if(d.type==='frame'){
      frameCount++; document.getElementById('frames').textContent=frameCount;
      document.getElementById('img').src='data:image/jpeg;base64,'+d.image;
      document.getElementById('app').textContent=(d.detected_app||'unknown').toUpperCase();
      document.getElementById('cid').textContent=d.content_id||'—';
      if(d.did_scroll){
        const now=Date.now();
        if(now-lastScrollTs>500){
          lastScrollTs=now;
          const b=document.getElementById('scrollBadge'); b.style.display='inline-block';
          document.getElementById('event').textContent='Scroll detected';
          setTimeout(()=>{b.style.display='none'},900);
        }
      }
    }
    if(d.type==='audio'){
      audioCount++; document.getElementById('audio').textContent=audioCount;
      document.getElementById('event').textContent='Audio chunk';
    }
  };
}
connect();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def ui():
    return HTML


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)


async def broadcast(msg: dict):
    for ws in active_connections[:]:
        try:
            await ws.send_json(msg)
        except:
            active_connections.remove(ws)


# ── App detection (OCR keywords; sticky to avoid flapping) ─────────────────────
KEYWORDS = {
    "tiktok": ["for you", "following", "tiktok"],
    "instagram": ["reels", "story", "instagram"],
    "youtube": ["subscribe", "shorts", "youtube"],
    "twitter": ["tweet", "retweet", "timeline", "repost", "x.com"],
}
STICKY_SECONDS = 12.0  # keep last confident app for this long


def aspect_vertical(im: Image.Image) -> bool:
    return (im.width / max(1, im.height)) < 0.7


def detect_app_raw(im: Image.Image) -> tuple[str, bool]:
    """
    Returns (app_name, confident).
    confident=True only if OCR explicitly matches keywords.
    """
    if not OCR:
        return ("short-form" if aspect_vertical(im) else "unknown", False)
    try:
        text = pytesseract.image_to_string(im).lower()
        for app, words in KEYWORDS.items():
            if any(w in text for w in words):
                return (app, True)
    except Exception:
        pass
    return ("short-form" if aspect_vertical(im) else "unknown", False)


def pick_sticky_app(im: Image.Image, now: float) -> str:
    new_app, confident = detect_app_raw(im)
    prev_app = session.get("current_app") or "unknown"

    if confident:
        session["last_confident_app_ts"] = now
        return new_app

    # No confident read:
    # If we had a confident app recently, keep it (avoid “short-form” bounce)
    last_ok = session.get("last_confident_app_ts", 0.0)
    if prev_app not in ("unknown", "short-form") and (now - last_ok) <= STICKY_SECONDS:
        return prev_app

    # Otherwise, fall back to raw guess
    return new_app


# ── Like count detection (OCR on small regions) ────────────────────────────────
LIKE_RE = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)([kKmM]?)")

# regions (percentages) where like counts typically appear (tuned coarsely)
LIKE_REGIONS = {
    # TikTok: right side stack ~ middle-right
    "tiktok": {"left": 0.78, "top": 0.40, "right": 0.96, "bottom": 0.75},
    # Instagram Reels: bottom-left/on-caption area-ish
    "instagram": {"left": 0.05, "top": 0.78, "right": 0.55, "bottom": 0.93},
    # YouTube Shorts: bottom-left near title
    "youtube": {"left": 0.05, "top": 0.78, "right": 0.55, "bottom": 0.93},
    # fallback for short-form unknown
    "short-form": {"left": 0.70, "top": 0.40, "right": 0.98, "bottom": 0.90},
}


def crop_percent(im: Image.Image, reg: dict) -> Image.Image:
    w, h = im.width, im.height
    box = (
        int(w * reg["left"]),
        int(h * reg["top"]),
        int(w * reg["right"]),
        int(h * reg["bottom"]),
    )
    return im.crop(box)


def normalize_like_token(n: str, suf: str) -> int:
    # "1.2" + "K" -> 1200 ; "1.2" + "M" -> 1_200_000 ; "1,234" -> 1234
    n = n.replace(",", ".")
    val = float(n)
    if suf.lower() == "k":
        val *= 1_000
    elif suf.lower() == "m":
        val *= 1_000_000
    return int(val + 0.5)


def detect_like_count(im: Image.Image, app: str) -> int | None:
    if not OCR:
        return None
    target = LIKE_REGIONS.get(app) or LIKE_REGIONS["short-form"]
    region = crop_percent(im, target).convert("L")
    try:
        text = pytesseract.image_to_string(region)
    except Exception:
        return None
    # find first plausible like token
    for m in LIKE_RE.finditer(text):
        n, suf = m.group(1), m.group(2)
        try:
            return normalize_like_token(n, suf)
        except Exception:
            continue
    return None


# ── Perceptual hash scroll detection (content change) ─────────────────────────
def phash64(im: Image.Image) -> int:
    small = im.convert("L").resize((8, 8))
    pix = list(small.getdata())
    avg = sum(pix) / 64.0
    h = 0
    for i, p in enumerate(pix):
        if p > avg:
            h |= 1 << i
    return h


def hamming(a: int, b: int) -> int:
    x = a ^ b
    c = 0
    while x:
        c += x & 1
        x >>= 1
    return c


def detect_scroll_phash(im: Image.Image, now: float, min_gap: float = 1.0) -> bool:
    h = phash64(im)
    prev = session.get("last_hash")
    session["last_hash"] = h
    if prev is None:
        return False
    dist = hamming(prev, h)
    looks_like_scroll = 8 <= dist <= 40
    if looks_like_scroll and (now - session.get("last_scroll_ts", 0.0) >= min_gap):
        session["last_scroll_ts"] = now
        return True
    return False


def detect_scroll_likes(
    im: Image.Image, app: str, now: float, min_gap: float = 1.0
) -> tuple[bool, int | None]:
    """Returns (did_scroll, like_value). Scroll if normalized like count changes."""
    like_val = detect_like_count(im, app)
    if like_val is None:
        return (False, None)
    prev_like = session.get("last_like")
    # tolerate tiny OCR jitter (e.g., 1234 vs 1233)
    changed = (prev_like is None) or (abs(like_val - prev_like) >= 5)
    if changed and (now - session.get("last_scroll_ts", 0.0) >= min_gap):
        session["last_like"] = like_val
        session["last_scroll_ts"] = now
        return (True, like_val)
    # update the cached like occasionally even if no change (keeps it fresh)
    if now - session.get("last_like_ts", 0.0) > 2.5:
        session["last_like"] = like_val
        session["last_like_ts"] = now
    return (False, like_val)


@app.post("/upload")
async def upload(req: Request):
    # Get raw body for debugging
    body = await req.body()

    try:
        data = json.loads(body)
    except Exception as e:
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

    t = data.get("type")

    if t == "video":
        return await handle_frame(data)
    if t == "audio":
        return await handle_audio(data)

    return JSONResponse({"ok": False, "error": f"unknown type: {t}"}, status_code=400)


async def handle_frame(d: dict):
    b64 = d.get("payload")
    if not b64:
        return JSONResponse({"ok": False, "error": "no payload"}, status_code=400)

    try:
        image_bytes = base64.b64decode(b64)
    except Exception as e:
        logger.error(f"❌ Failed to decode video base64: {e}")
        return JSONResponse({"ok": False, "error": "invalid base64"}, status_code=400)

    # Generate metadata server-side
    timestamp = datetime.utcnow().isoformat() + "Z"
    session["frames"] = session.get("frames", 0) + 1
    frame_number = session["frames"]

    # Initialize session if needed
    if not session.get("session_id"):
        session["session_id"] = str(uuid.uuid4())
        session["content_id"] = str(uuid.uuid4())

    # persist (optional)
    ts_clean = timestamp.replace(":", "-").replace(".", "-")
    fn = f"captured_frames/frame_{frame_number:05d}_{ts_clean}.jpg"
    try:
        with open(fn, "wb") as f:
            f.write(image_bytes)
    except Exception:
        pass

    # open image once
    try:
        im = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return JSONResponse({"ok": False, "error": "bad image"}, status_code=400)

    now = time.time()

    # Sticky app detection (prevents bouncing to "short-form")
    app_name = pick_sticky_app(im, now)

    # Two ways to detect new content:
    # 1) pHash change (visual diff)
    sc_phash = detect_scroll_phash(im, now, min_gap=1.0)
    # 2) Like-count change (OCR numeric diff)
    sc_like, like_val = detect_scroll_likes(im, app_name, now, min_gap=1.0)

    did_scroll = bool(sc_phash or sc_like)
    if did_scroll or not session.get("content_id"):
        session["content_id"] = str(uuid.uuid4())

    # update session
    session["current_app"] = app_name

    await broadcast(
        {
            "type": "frame",
            "frame_number": frame_number,
            "session_id": session["session_id"],
            "content_id": session["content_id"],
            "timestamp": timestamp,
            "image": b64,
            "detected_app": app_name,
            "did_scroll": did_scroll,
        }
    )

    mark = "🔄 " if did_scroll else ""
    like_dbg = f" like={like_val}" if like_val is not None else ""
    logger.info(
        f"{mark}Frame {frame_number:05d}  app={app_name:<10}  content={session['content_id'][:8]}{like_dbg}"
    )
    return JSONResponse({"ok": True})


async def handle_audio(d: dict):
    b64 = d.get("payload")
    if not b64:
        return JSONResponse({"ok": False, "error": "no payload"}, status_code=400)

    try:
        bytes_ = base64.b64decode(b64)
    except Exception as e:
        logger.error(f"❌ Failed to decode audio base64: {e}")
        return JSONResponse({"ok": False, "error": "invalid base64"}, status_code=400)

    session["audio"] = session.get("audio", 0) + 1

    # Generate metadata server-side
    timestamp = datetime.utcnow().isoformat() + "Z"
    ts_clean = timestamp.replace(":", "-").replace(".", "-")

    try:
        # Save as WAV (the Swift code sends WAV format)
        with open(
            f"captured_audio/audio_{session['audio']:05d}_{ts_clean}.wav", "wb"
        ) as f:
            f.write(bytes_)
    except Exception:
        pass

    await broadcast(
        {
            "type": "audio",
            "timestamp": timestamp,
            "content_id": session.get("content_id"),
            "size_kb": round(len(bytes_) / 1024, 1),
        }
    )
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import socket

    ip = socket.gethostbyname(socket.gethostname())
    logger.info("\n============================================================")
    logger.info("BrainRot Monitor - Minimal Server")
    logger.info("Open GUI:      http://{}:8000".format(ip))
    logger.info("iOS endpoint:  http://{}:8000/upload".format(ip))
    logger.info("============================================================\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
