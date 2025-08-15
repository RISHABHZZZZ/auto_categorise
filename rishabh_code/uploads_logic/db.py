# db.py
from __future__ import annotations
import os
from typing import List, Dict, Any, Tuple, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from dotenv import load_dotenv

# Optional: register pgvector so embeddings come back as lists
try:
    from pgvector.psycopg2 import register_vector
    _HAS_VECTOR = True
except Exception:
    _HAS_VECTOR = False

load_dotenv()

CFG = {
    "host": os.getenv("PGHOST", "127.0.0.1"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "ragdb"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

def connect():
    conn = psycopg2.connect(**CFG)
    if _HAS_VECTOR:
        with conn.cursor() as cur:
            register_vector(cur)
    return conn

def get_documents(status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    q = ["SELECT id, document_name, canonical_slug, top_entity, org_variant, state_variant, confidence, status FROM documents"]
    params: List[Any] = []
    if status:
        q.append("WHERE status = %s")
        params.append(status)
    q.append("ORDER BY id ASC")
    if limit:
        q.append("LIMIT %s")
        params.append(limit)
    sql_q = " ".join(q)
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql_q, params)
        return list(cur.fetchall())

def get_document(doc_id: int) -> Optional[Dict[str, Any]]:
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM documents WHERE id=%s", (doc_id,))
        return cur.fetchone()

def chunks_table_exists(doc_id: int) -> bool:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.chunks_{doc_id}",))
        return cur.fetchone()[0] is not None

def get_chunks(doc_id: int, limit: Optional[int] = None) -> List[Tuple[int, str, list]]:
    tbl = sql.Identifier(f"chunks_{doc_id}")
    base = sql.SQL("SELECT id, chunk, embedding FROM {} ORDER BY id ASC").format(tbl)
    q = base if limit is None else sql.SQL("SELECT id, chunk, embedding FROM {} ORDER BY id ASC LIMIT %s").format(tbl)
    with connect() as conn, conn.cursor() as cur:
        if limit is None:
            cur.execute(q)
        else:
            cur.execute(q, (limit,))
        return cur.fetchall()

def update_match(doc_id: int, *, slug: Optional[str], top_entity: Optional[str],
                 org_variant: Optional[str], state_variant: Optional[str],
                 confidence: Optional[float], status: str) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE documents
               SET canonical_slug = %s,
                   top_entity = %s,
                   org_variant = %s,
                   state_variant = %s,
                   confidence = %s,
                   status = %s,
                   updated_at = now()
             WHERE id = %s
            """,
            (slug, top_entity, org_variant, state_variant, confidence, status, doc_id)
        )
        conn.commit()

def list_chunk_tables() -> List[int]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT regexp_replace(table_name, '^chunks_', '')::int AS doc_id
              FROM information_schema.tables
             WHERE table_schema='public' AND table_name ~ '^chunks_[0-9]+$'
             ORDER BY 1;
        """)
        return [r[0] for r in cur.fetchall()]

# db.py (add at bottom)
def filename_counts() -> Dict[str,int]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT lower(document_name), COUNT(*) FROM documents GROUP BY 1;")
        return {name: cnt for (name, cnt) in cur.fetchall()}
