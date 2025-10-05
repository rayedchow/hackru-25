from datasetup import gemini_model, embed_text, graph_driver, pg
import json

COMM_PROMPT = """You are summarizing a cluster of user-consumed short-form reels.
Topics: {topics}
Representative clip ids: {sample}
Return a concise 2–3 sentence summary highlighting what unifies this community, typical aesthetics/content types (if clear), and what a learner could analogize from it.
"""

with open("queries/community_match.txt", "r") as f:
    COMM_MATCH = f.read()


def summarize_and_index_communities():
    with graph_driver.session() as s, pg.cursor() as cur:
        for rec in s.run(COMM_MATCH):
            cid = str(rec["community_id"])
            topics = rec["topics"] or []
            sample = rec["sample_clips"] or []
            prompt = COMM_PROMPT.format(
                topics=", ".join(topics), sample=", ".join(sample)
            )
            txt = gemini_model.generate_content(prompt).text.strip()
            emb = embed_text(txt)["embedding"]
            topk = {"topics": topics[:10], "sample_clips": sample}
            cur.execute(
                """
            INSERT INTO community_reports (community_id, size, level, summary, top_k, emb)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (community_id) DO UPDATE SET
              size=EXCLUDED.size, level=EXCLUDED.level, summary=EXCLUDED.summary, top_k=EXCLUDED.top_k, emb=EXCLUDED.emb
            """,
                (cid, rec["size"], 0, txt, json.dumps(topk), emb),
            )
    print("Indexed community summaries.")
