from datasetup import embed_text, gemini_model, pg
import json, sys
from projector import pca_3d


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
                   1 - cosine_distance(emb, %s::vector(768)) AS score
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
        return [dict(zip([d.name for d in cur.description], row)) for row in rows]


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
                   1 - cosine_distance(emb, %s::vector(768)) AS score
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
        from datasetup import pg

        with pg.cursor() as cur:
            if comms and missing_comm_emb:
                ids = tuple([c["community_id"] for c in comms])
                cur.execute(
                    "SELECT community_id, emb FROM community_reports WHERE community_id IN %s",
                    (ids,),
                )
                emb_map = {r[0]: r[1] for r in cur.fetchall()}
                for c in comms:
                    c.setdefault("embedding", emb_map.get(c["community_id"]))
            if cards and missing_card_emb:
                ids = tuple([c["clip_id"] for c in cards])
                cur.execute(
                    "SELECT clip_id, emb FROM image_cards WHERE clip_id IN %s", (ids,)
                )
                emb_map = {r[0]: r[1] for r in cur.fetchall()}
                for c in cards:
                    c.setdefault("embedding", emb_map.get(c["clip_id"]))

    # 3D projection (fit on the combined set so both lie in the same space)
    if project_to_3d:
        all_vecs = []
        idx_comm, idx_card = [], []
        for i, c in enumerate(comms):
            if c.get("embedding") is not None:
                idx_comm.append(len(all_vecs))
                all_vecs.append(c["embedding"])
        for i, c in enumerate(cards):
            if c.get("embedding") is not None:
                idx_card.append(len(all_vecs))
                all_vecs.append(c["embedding"])

        if all_vecs:
            Z = pca_3d(all_vecs)  # or umap_3d(all_vecs)
            for k, i_global in enumerate(idx_comm):
                comms[k]["coords3d"] = Z[i_global].tolist()
            for k, i_global in enumerate(idx_card):
                cards[k]["coords3d"] = Z[i_global].tolist()

    # Build the teaching prompt
    prompt = f"""
      You are a teacher and a storyteller who understands the user's learning style through their media consumption.
      Your task is to teach the user the concept in the query in a way that is deeply engaging and emotionally resonant.

      Global community summaries:
      {json.dumps(comms, indent=2)}

      Representative image cards:
      {json.dumps(cards, indent=2)}

      Now, explain the concept in the query below as if you are speaking directly to this user,
      weaving their media patterns into your teaching as natural, flowing analogies — not separate sections.

      Guidelines:
      - Use a narrative tone and vivid analogies.
      - Integrate at least two analogies from the above media patterns.
      - Avoid mentioning "reels" or "feed".
      - Output three concise sections with markdown headings:
        1. A Hook or Analogy
        2. The Core Explanation
        3. The Connection

      Query:
      {query}
    """.strip()

    answer = (gemini_model.generate_content(prompt).text or "").strip()

    return {
        "answer": answer,
        "communities": comms,  # each may now have coords3d
        "cards": cards,  # each may now have coords3d
        "projection": "pca_3d",
    }


if __name__ == "__main__":
    print(ask("I'm taking Calculus. Explain what a derivative is."))
