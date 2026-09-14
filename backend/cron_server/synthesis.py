from cron_server.datasetup import embed_text, gemini_model, pg
import json, sys
from cron_server.projector import pca_3d


def _parse_pg_vector(vec_str):
    """Parse PostgreSQL vector string format '[1.0,2.0,...]' to list of floats."""
    if isinstance(vec_str, str):
        # Remove brackets and split by comma
        vec_str = vec_str.strip()
        if vec_str.startswith("[") and vec_str.endswith("]"):
            vec_str = vec_str[1:-1]
        return [float(x) for x in vec_str.split(",")]
    return vec_str  # already a list/array


def _vec_literal(vec):
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def search_cards_pg(query_text, topk=10):
    vec = embed_text(query_text)["embedding"]
    probe = _vec_literal(vec)
    with pg.cursor() as cur:
        cur.execute(
            """
            -- cosine distance via function (works across pgvector versions)
            SELECT clip_id, brief_caption, subject, aesthetic, trend, celebrity, content_type,
                   1 - cosine_distance(emb, %s::vector(768)) AS score,
                   emb
            FROM image_cards
            WHERE emb IS NOT NULL
            ORDER BY cosine_distance(emb, %s::vector(768))
            LIMIT %s
            """,
            (probe, probe, topk),
        )
        rows = cur.fetchall()
        if not rows:
            print("[cards] vector search returned 0 rows", file=sys.stderr)
        results = []
        for row in rows:
            item = dict(zip([d.name for d in cur.description], row))
            # Parse the embedding from PostgreSQL vector format
            if "emb" in item and item["emb"] is not None:
                item["embedding"] = _parse_pg_vector(item["emb"])
                del item["emb"]  # Remove the raw emb field
            results.append(item)
        return results


def search_communities_pg(query_text, topk=6):
    vec = embed_text(query_text)["embedding"]
    probe = _vec_literal(vec)
    with pg.cursor() as cur:
        cur.execute("SELECT to_regclass('public.community_reports')")
        if cur.fetchone()[0] is None:
            print("[comms] community_reports table missing", file=sys.stderr)
            return []
        cur.execute("SELECT count(*) FROM community_reports WHERE emb IS NOT NULL")
        if cur.fetchone()[0] == 0:
            print("[comms] no community embeddings present", file=sys.stderr)
            return []

        cur.execute(
            """
            SELECT community_id, summary, top_k,
                   1 - cosine_distance(emb, %s::vector(768)) AS score,
                   emb
            FROM community_reports
            WHERE emb IS NOT NULL
            ORDER BY cosine_distance(emb, %s::vector(768))
            LIMIT %s
            """,
            (probe, probe, topk),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        out = []
        for r in rows:
            item = dict(zip(cols, r))
            if isinstance(item["top_k"], str):
                item["top_k"] = json.loads(item["top_k"])
            # Parse the embedding from PostgreSQL vector format
            if "emb" in item and item["emb"] is not None:
                item["embedding"] = _parse_pg_vector(item["emb"])
                del item["emb"]  # Remove the raw emb field
            out.append(item)
        if not out:
            print("[comms] vector search returned 0 rows", file=sys.stderr)
        return out


def ask(query: str, project_to_3d: bool = True):
    # Retrieve
    comms = search_communities_pg(
        query, topk=4
    )  # should include 'embedding' if you added earlier patch
    cards = search_cards_pg(query, topk=4)

    # Ensure embeddings are present; if not, fetch them just like you did before
    missing_comm_emb = any(
        "embedding" not in c or c["embedding"] is None for c in comms
    )
    missing_card_emb = any(
        "embedding" not in c or c["embedding"] is None for c in cards
    )

    if missing_comm_emb or missing_card_emb:
        with pg.cursor() as cur:
            if comms and missing_comm_emb:
                ids = [c["community_id"] for c in comms]
                cur.execute(
                    "SELECT community_id, emb FROM community_reports WHERE community_id = ANY(%s)",
                    (ids,),
                )
                emb_map = {r[0]: _parse_pg_vector(r[1]) for r in cur.fetchall()}
                for c in comms:
                    c.setdefault("embedding", emb_map.get(c["community_id"]))
            if cards and missing_card_emb:
                ids = [c["clip_id"] for c in cards]
                cur.execute(
                    "SELECT clip_id, emb FROM image_cards WHERE clip_id = ANY(%s)",
                    (ids,),
                )
                emb_map = {r[0]: _parse_pg_vector(r[1]) for r in cur.fetchall()}
                for c in cards:
                    c.setdefault("embedding", emb_map.get(c["clip_id"]))

    # 3D projection (fit on the combined set so both lie in the same space)
    if project_to_3d:
        all_vecs = []
        # (index into comms/cards, row index in all_vecs) — items without an
        # embedding are skipped, so the two indices are not interchangeable.
        idx_comm, idx_card = [], []
        for i, c in enumerate(comms):
            if c.get("embedding") is not None:
                idx_comm.append((i, len(all_vecs)))
                all_vecs.append(c["embedding"])
        for i, c in enumerate(cards):
            if c.get("embedding") is not None:
                idx_card.append((i, len(all_vecs)))
                all_vecs.append(c["embedding"])

        if all_vecs:
            Z = pca_3d(all_vecs)  # or umap_3d(all_vecs)
            for i_item, i_global in idx_comm:
                comms[i_item]["coords3d"] = Z[i_global].tolist()
            for i_item, i_global in idx_card:
                cards[i_item]["coords3d"] = Z[i_global].tolist()

    # Create clean copies for prompt (no embeddings or coords3d)
    comms_for_prompt = []
    for c in comms:
        c_clean = {k: v for k, v in c.items() if k not in ["embedding", "coords3d"]}
        comms_for_prompt.append(c_clean)

    cards_for_prompt = []
    for c in cards:
        c_clean = {k: v for k, v in c.items() if k not in ["embedding", "coords3d"]}
        cards_for_prompt.append(c_clean)

    # Build the teaching prompt
    prompt = f"""
      You are a teacher and a storyteller who understands the user's learning style through their media consumption.
      Your task is to teach the user the concept in the query in a way that is deeply engaging and emotionally resonant.

      Global community summaries:
      {json.dumps(comms_for_prompt, indent=2)}

      Representative image cards:
      {json.dumps(cards_for_prompt, indent=2)}

      Now, explain the concept in the query below as if you are speaking directly to this user,
      weaving their media patterns into your teaching as natural, flowing analogies — not separate sections.

      Guidelines:
      - Use a narrative tone and vivid analogies.
      - Integrate at least two analogies from the above media patterns.
      - Avoid mentioning "reels" or "feed" or "analogy".
      - Keep it extremely smooth and concisely answer the query by seamlessly connecting to the relationship-wise relevant media above.

      Query:
      {query}
    """.strip()

    answer = (gemini_model.generate_content(prompt).text or "").strip()

    # Remove embeddings from response (only keep coords3d for visualization)
    for c in comms:
        c.pop("embedding", None)
    for c in cards:
        c.pop("embedding", None)

    return {
        "answer": answer,
        "communities": comms,  # each may now have coords3d
        "cards": cards,  # each may now have coords3d
        "projection": "pca_3d",
    }


if __name__ == "__main__":
    print(ask("I'm taking Calculus. Explain what a derivative is."))
