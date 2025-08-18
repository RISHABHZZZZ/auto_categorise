# sanity_test.py
import os
from source_of_truth import load_sot, filter_by_state, by_slug
from db import get_documents, get_document, get_chunks, chunks_table_exists

state = os.getenv("STATE_DEFAULT", "TS")
cats = load_sot()
cands = filter_by_state(cats, state)
print(f"Loaded {len(cats)} SoT entries; {len(cands)} candidates for state={state}")

docs = get_documents(limit=5)
print("Sample docs:", [(d["id"], d["document_name"], d["status"]) for d in docs])

if docs:
    doc_id = docs[0]["id"]
    print(f"Testing chunks for doc_id={doc_id} ... exists? {chunks_table_exists(doc_id)}")
    if chunks_table_exists(doc_id):
        rows = get_chunks(doc_id, limit=2)
        print("First 2 chunks:", [(r[0], len(r[1]), len(r[2])) for r in rows])  # (chunk_id, text_len, emb_len)
