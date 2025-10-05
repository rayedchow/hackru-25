import os
import re
import json
from datetime import datetime

from datasetup import (
    graph_driver,
    gemini_model,
    pg,
    embed_text,
)  # your existing objects

CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.5"))

# ------------------- prompts / scripts -------------------
with open("queries/vector_generation.txt", "r") as f:
    VECTOR_GENERATION_PROMPT = f.read()

with open("queries/graph_upsert.txt", "r") as f:
    GRAPH_UPSERT_GENERATION = f.read()

with open("queries/cross_edges.txt", "r") as f:
    CROSS_EDGES_GENERATION = f.read()

# Set card text on Clip immediately after upsert
CYPHER_SET_CARD = """
MATCH (c:Clip {id:$clip_id})
SET c.card = $card
"""


# ------------------- helpers -------------------
def _find_json_payload(text: str):
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    first = min(
        [i for i in [cleaned.find("{"), cleaned.find("[")] if i != -1], default=-1
    )
    last = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if first != -1 and last != -1 and last > first:
        return json.loads(cleaned[first : last + 1])
    raise ValueError("Could not parse JSON from model output")


def _iso_yearweek(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _filter_conf(items, k=None):
    out = [
        x
        for x in (items or [])
        if isinstance(x, dict) and x.get("conf", 0) >= CONF_THRESHOLD and x.get("name")
    ]
    return out[:k] if k else out


def _prepare_params(clip_obj: dict, fallback_clip_id: str | None = None):
    now = datetime.utcnow()
    clip_id = (
        clip_obj.get("clip_id") or fallback_clip_id or f"clip_{int(now.timestamp())}"
    )
    saved_at = now.isoformat() + "Z"
    timebin = _iso_yearweek(now)
    subjects = _filter_conf(clip_obj.get("subject"), k=3)
    aesthetics = _filter_conf(clip_obj.get("aesthetic"), k=3)
    trends = _filter_conf(clip_obj.get("trend"), k=3)
    celebs = _filter_conf(clip_obj.get("celebrity"), k=3)
    events = _filter_conf(clip_obj.get("current_event"), k=3)
    ctypes = _filter_conf(clip_obj.get("content_type"), k=1)
    for t in trends:
        t.setdefault("phase", "stable")
    return {
        "clip_id": clip_id,
        "saved_at": saved_at,
        "timebin": timebin,
        "subjects": subjects,
        "aesthetics": aesthetics,
        "trends": trends,
        "celebs": celebs,
        "events": events,
        "ctypes": ctypes,
    }


# ----------- CARD: build a short, stable, LLM-friendly string -----------
def _first_or_blank(arr):  # arr = [{'name':..., 'conf':...}]
    return arr[0]["name"] if arr else ""


def build_card_from_params(params: dict) -> str:
    # keep it compact; consistent key order helps embedding quality
    subject = _first_or_blank(params.get("subjects"))
    aesthetic = _first_or_blank(params.get("aesthetics"))
    trend = _first_or_blank(params.get("trends"))
    celebrity = _first_or_blank(params.get("celebs"))
    current_event = _first_or_blank(params.get("events"))
    content_type = _first_or_blank(params.get("ctypes"))
    parts = []
    if subject:
        parts.append(f"subject:{subject}")
    if aesthetic:
        parts.append(f"aesthetic:{aesthetic}")
    if trend:
        parts.append(f"trend:{trend}")
    if celebrity:
        parts.append(f"celebrity:{celebrity}")
    if current_event:
        parts.append(f"event:{current_event}")
    if content_type:
        parts.append(f"type:{content_type}")
    parts.append(f"timebin:{params['timebin']}")  # light temporal anchor
    return " | ".join(parts)


# ----------- OPTIONAL: pgvector indexing -----------
SQL_ENSURE = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS image_cards (
  clip_id       text PRIMARY KEY,
  timebin       text,
  subject       text,
  aesthetic     text,
  trend         text,
  celebrity     text,
  current_event text,
  content_type  text,
  brief_caption text,
  emb           vector(768)
);
CREATE INDEX IF NOT EXISTS idx_image_cards_emb
ON image_cards USING ivfflat (emb vector_cosine_ops) WITH (lists=100);
"""


def _embed_text_768(text: str):
    # Uses Gemini embeddings; requires GOOGLE_API_KEY
    # Model name can be adjusted (e.g., "text-embedding-004")
    res = embed_text(text)
    return res["embedding"]  # list[float]


def _pg_upsert_card(pg_conn, clip_id: str, timebin: str, card: str, params: dict):
    subj = _first_or_blank(params.get("subjects"))
    aest = _first_or_blank(params.get("aesthetics"))
    trnd = _first_or_blank(params.get("trends"))
    celb = _first_or_blank(params.get("celebs"))
    evnt = _first_or_blank(params.get("events"))
    ctyp = _first_or_blank(params.get("ctypes"))
    vec = _embed_text_768(card)
    with pg_conn.cursor() as cur:
        if vec is None:
            cur.execute(
                """
            INSERT INTO image_cards (clip_id, timebin, subject, aesthetic, trend, celebrity, current_event, content_type, brief_caption)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (clip_id) DO UPDATE SET
              timebin=EXCLUDED.timebin, subject=EXCLUDED.subject, aesthetic=EXCLUDED.aesthetic,
              trend=EXCLUDED.trend, celebrity=EXCLUDED.celebrity, current_event=EXCLUDED.current_event,
              content_type=EXCLUDED.content_type, brief_caption=EXCLUDED.brief_caption
            """,
                (clip_id, timebin, subj, aest, trnd, celb, evnt, ctyp, card),
            )
        else:
            cur.execute(
                """
            INSERT INTO image_cards (clip_id, timebin, subject, aesthetic, trend, celebrity, current_event, content_type, brief_caption, emb)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (clip_id) DO UPDATE SET
              timebin=EXCLUDED.timebin, subject=EXCLUDED.subject, aesthetic=EXCLUDED.aesthetic,
              trend=EXCLUDED.trend, celebrity=EXCLUDED.celebrity, current_event=EXCLUDED.current_event,
              content_type=EXCLUDED.content_type, brief_caption=EXCLUDED.brief_caption, emb=EXCLUDED.emb
            """,
                (clip_id, timebin, subj, aest, trnd, celb, evnt, ctyp, card, vec),
            )


def _maybe_init_pg():
    if not pg:
        return None
    with pg.cursor() as cur:
        cur.execute(SQL_ENSURE)
    return pg


# ------------------- core upsert flow -------------------
def upsert_records_to_graph(records, content_id):
    """
    records: list[dict] following your schema
    content_id: the clip id to use if Gemini didn't return one
    """
    pg_conn = _maybe_init_pg()
    with graph_driver.session() as session:
        for rec in records:
            params = _prepare_params(rec, fallback_clip_id=content_id)
            # 1) Upsert nodes/edges
            session.run(GRAPH_UPSERT_GENERATION, **params)
            session.run(CROSS_EDGES_GENERATION, clip_id=params["clip_id"])
            # 2) Build card from the just-upserted params
            card = build_card_from_params(params)
            session.run(CYPHER_SET_CARD, clip_id=params["clip_id"], card=card)
            # 3) OPTIONAL: index card in pgvector immediately
            if pg_conn:
                _pg_upsert_card(
                    pg_conn, params["clip_id"], params["timebin"], card, params
                )

    if pg_conn:
        pg_conn.commit()


# ------------------- Gemini call -------------------
def upsert_content(images, content_id):
    upsert_input = [VECTOR_GENERATION_PROMPT]
    for image in images:
        upsert_input.append(image)
    upsert_input.append(
        "Return a JSON array of per-image objects strictly following the schema."
    )
    response = gemini_model.generate_content(upsert_input)
    raw_text = (response.text or "").strip()
    data = _find_json_payload(raw_text)
    records = (
        [data] if isinstance(data, dict) else data if isinstance(data, list) else None
    )
    if records is None:
        raise ValueError("Parsed JSON is neither an object nor an array")
    upsert_records_to_graph(records, content_id)
    print(
        f"Upserted {len(records)} record(s) to Neo4j and created cards"
        + (" + pgvector" if pg else "")
    )
