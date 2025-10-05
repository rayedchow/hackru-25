from datasetup import embed_text, gemini_model, pg
import json, sys


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


def ask(query: str):
    comms = search_communities_pg(query, topk=4)  # sense-making layer
    cards = search_cards_pg(query, topk=4)  # concrete examples
    prompt = f"""
      You are a teacher and a storyteller who understands the user's learning style through their media consumption.
      Your task is to teach the user the concept in the query in a way that is deeply engaging and emotionally resonant.

      The user has consumed the following media communities and content cards:
      Global community summaries (contextual themes of what they watch):
      {json.dumps(comms, indent=2)}

      Representative image cards (specific examples of content they engage with):
      {json.dumps(cards, indent=2)}

      Now, explain the concept in the query below **as if you are speaking directly to this user**, 
      weaving their media patterns into your teaching as natural, flowing analogies — not separate sections. 
      Each analogy should feel like a story that makes the educational concept *click* through the lens of what they watch.

      **Guidelines:**
      - Write in a narrative, human tone — think like a wise, reflective teacher who uses pop culture to teach deeply.
      - Integrate at least two analogies from the media patterns above in a cohesive way, rather than listing them.
      - Do NOT say things like "reels" or "feed", just SMOOTHLY CONNECT THE CONCEPT TO THE USER'S MEDIA CONSUMPTION. DO IT IN A WAY THAT IS NATURAL AND NOT FORCEFUL.
      - Use vivid examples and emotional connection, not bullet points.
      - Make it sound inspiring and intuitive, as if this concept were already embedded in their daily life.
      - MAKE YOUR RESPONSE TO THE POINT.
      - Output 3 short sections with markdown headings:
        1. A Hook or Analogy
        2. The Core Explanation
        3. The Connection — showing how the concept lives inside their media consumption.

      **Query:**
      {query}"""
    return gemini_model.generate_content(prompt).text.strip()


if __name__ == "__main__":
    print(ask("I'm taking Calculus. Explain what a derivative is."))
