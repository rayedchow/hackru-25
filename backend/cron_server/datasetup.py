import google.generativeai as genai
from dotenv import load_dotenv
import os
import psycopg

from neo4j import GraphDatabase

load_dotenv()

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-2.0-flash-001")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
PG_DSN = os.getenv("PG_DSN")

graph_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
pg = psycopg.connect(PG_DSN, autocommit=True)


def embed_text(text: str):
    return genai.embed_content(model="text-embedding-004", content=text)
