# streamlit_app.py
from __future__ import annotations
import io
import contextlib
from typing import Dict, List

import streamlit as st
import pandas as pd

# -------------------- page setup --------------------
st.set_page_config(page_title="Auto Category • Demo UI", layout="wide")
st.title("Autocategorization • POC UI")
st.write("Use the buttons below to run steps. Errors will show inline if anything fails.")

# -------------------- sidebar -----------------------
st.sidebar.title("Controls")
state = st.sidebar.selectbox("State variant", ["TS", "KA"], index=0)
limit = st.sidebar.slider("Batch size (for testing)", 5, 200, 30, step=5)
apply = st.sidebar.checkbox("Write results to DB (apply)", value=False)
show_topk = st.sidebar.slider("Show Top-K per doc", 1, 5, 3)

# -------------------- safe imports ------------------
def try_imports():
    try:
        from dotenv import load_dotenv
        from source_of_truth import load_sot, filter_by_state
        from resolver import categorize_document, build_category_vectors
        from db import get_documents, get_chunks, update_match, filename_counts
        import entity_role_infer as eri  # import module, then take .run

        if not hasattr(eri, "run"):
            raise ImportError("entity_role_infer.run not found")

        load_dotenv()
        return {
            "load_sot": load_sot,
            "filter_by_state": filter_by_state,
            "categorize_document": categorize_document,
            "build_category_vectors": build_category_vectors,
            "get_documents": get_documents,
            "get_chunks": get_chunks,
            "update_match": update_match,
            "filename_counts": filename_counts,
            "infer_roles_run": eri.run,
        }, None
    except Exception as e:
        return None, e

imports, err = try_imports()
if err:
    st.error("Import failed. Check missing packages or local modules.")
    st.exception(err)
    st.stop()

# unpack
load_sot = imports["load_sot"]
filter_by_state = imports["filter_by_state"]
categorize_document = imports["categorize_document"]
build_category_vectors = imports["build_category_vectors"]
get_documents = imports["get_documents"]
get_chunks = imports["get_chunks"]
update_match = imports["update_match"]
filename_counts = imports["filename_counts"]
infer_roles_run = imports["infer_roles_run"]

# -------------------- helpers -----------------------
@st.cache_data(show_spinner=False)
def cached_sot_and_vecs(state: str):
    cats = filter_by_state(load_sot(), state)
    # In case sentence-transformers isn't installed, keep going without S3
    try:
        vecs = build_category_vectors(cats)  # may be {}
    except Exception:
        vecs = {}
    return cats, vecs

@st.cache_data(show_spinner=False)
def cached_filename_counts() -> Dict[str, int]:
    return filename_counts()

def df_from_results(results: List[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "id": r["doc_id"],
            "document_name": r["document_name"],
            "best_display": r["best_display"],
            "best_slug": r["best_slug"],
            "top_entity": r["top_entity"],
            "org_variant": r["org_variant"],
            "state_variant": r["state_variant"],
            "final": r["final"],
            "s1": r["s1"],
            "s2": r["s2"],
            "s3": r["s3"],
            "status": r["status"],
            "dup_name": r.get("is_dup_name", False),
            "generic_name": r.get("is_generic_name", False),
            "w_s1": r["weights"]["s1"],
            "w_s2": r["weights"]["s2"],
            "w_s3": r["weights"]["s3"],
        })
    return pd.DataFrame(rows).sort_values(by=["status", "final"], ascending=[True, False])

# -------------------- section 1: categorize ----------
st.header("1) Categorize documents")
colA, colB = st.columns([1, 1])
with colA:
    run_btn = st.button("Run categorization", type="primary", use_container_width=True)
with colB:
    refresh_btn = st.button("Refresh DB table", use_container_width=True)

# Live fetch & coerce rows to dicts (avoid RealDictRow attribute errors)
try:
    docs_rows = [dict(d) for d in get_documents(limit=None)]
except Exception as e:
    st.error("DB fetch failed. Verify connection/env vars.")
    st.exception(e)
    docs_rows = []

docs_df = pd.DataFrame([{
    "id": d["id"],
    "document_name": d["document_name"],
    "canonical_slug": d.get("canonical_slug"),
    "top_entity": d.get("top_entity"),
    "org_variant": d.get("org_variant"),
    "state_variant": d.get("state_variant"),
    "confidence": d.get("confidence"),
    "status": d.get("status"),
} for d in docs_rows])

if run_btn:
    try:
        cats, vecs = cached_sot_and_vecs(state)
        fname_cnts = cached_filename_counts()
        st.info(f"Loaded {len(cats)} categories for state={state}. Starting…")

        # pull a fresh limited batch
        sample = [dict(d) for d in get_documents(limit=limit)]
        results: List[dict] = []
        progress = st.progress(0.0)

        for i, row in enumerate(sample, start=1):
            res = categorize_document(
                row,
                cats,
                vecs,
                fname_cnts,
                state_variant=state,
                topk_show=show_topk,
            )
            results.append(res)

            st.write(
                f"**#{res['doc_id']}** `{res['document_name']}` → "
                f"{res['best_display']} ({res['best_slug']}) • "
                f"score={res['final']:.3f} • status={res['status']} "
                f"{'(rule boost)' if res.get('rule') else ''}"
            )

            if apply:
                update_match(
                    row["id"],
                    slug=res["best_slug"],
                    top_entity=res["top_entity"],
                    org_variant=res["org_variant"],
                    state_variant=res["state_variant"],
                    confidence=res["final"],
                    status=res["status"],
                )

            progress.progress(i / max(1, len(sample)))

        st.success(f"Done. {'Applied to DB' if apply else 'Dry run only'} for {len(results)} docs.")
        st.subheader("Batch summary")
        st.dataframe(df_from_results(results), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error("Categorization run failed.")
        st.exception(e)

# -------------------- section 2: inspect -------------
st.header("2) Inspect a single document")
if docs_rows:
    left, right = st.columns([2, 1])
    with left:
        options = {f"#{d['id']} • {d['document_name']}": d["id"] for d in docs_rows}
        pick = st.selectbox("Pick", list(options.keys()))
    with right:
        inspect_btn = st.button("Analyze selected")

    if inspect_btn:
        try:
            doc_id = options[pick]
            row = next(d for d in docs_rows if d["id"] == doc_id)
            cats, vecs = cached_sot_and_vecs(state)
            fname_cnts = cached_filename_counts()
            res = categorize_document(row, cats, vecs, fname_cnts, state_variant=state, topk_show=show_topk)

            st.write(f"**Result:** {res['best_display']} (`{res['best_slug']}`) • score={res['final']:.3f} • status={res['status']}")
            st.caption(
                f"Weights s1/s2/s3 = {res['weights']} • "
                f"duplicate filename={res.get('is_dup_name', False)} • "
                f"generic={res.get('is_generic_name', False)}"
            )
            st.write("**Top-K**")
            st.dataframe(pd.DataFrame(res["topk"]), use_container_width=True, hide_index=True)

            chunks = get_chunks(doc_id)[:1]
            if chunks:
                st.write("**First page (text preview):**")
                st.code(chunks[0][1][:2000])
        except Exception as e:
            st.error("Inspect failed.")
            st.exception(e)
else:
    st.info("No documents found in DB.")

# -------------------- section 3: manual override -----
st.header("3) Manual override (one doc)")
if docs_rows:
    ov_col1, ov_col2, ov_col3, ov_col4 = st.columns([2, 2, 1, 1])
    with ov_col1:
        doc_map = {f"#{d['id']} • {d['document_name']}": d["id"] for d in docs_rows}
        ov_choice = st.selectbox("Doc to override", list(doc_map.keys()))
    with ov_col2:
        cats_all, _ = cached_sot_and_vecs(state)
        slug_map = {f"{c.top_entity} • {c.display} ({c.slug})": c.slug for c in cats_all}
        new_slug = st.selectbox("Set canonical slug", list(slug_map.keys()))
    with ov_col3:
        new_top = st.selectbox(
            "Top entity",
            [
                "developer_entity",
                "group_entity",
                "directors_partners",
                "project_land_documents",
                "project_approvals_documents",
                "legal_documents",
                "other_project_documents",
            ],
        )
    with ov_col4:
        new_org = st.selectbox("Org variant", ["company", "partnership", "llp", "na"])

    apply_override = st.button("Apply override", type="secondary")
    if apply_override and ov_choice and new_slug:
        try:
            doc_id = doc_map[ov_choice]
            cslug = slug_map[new_slug]
            update_match(
                doc_id,
                slug=cslug,
                top_entity=new_top,
                org_variant=new_org,
                state_variant=state,
                confidence=None,
                status="needs_review",
            )
            st.success(f"Updated #{doc_id} → {cslug} • {new_top} • {new_org}")
        except Exception as e:
            st.error("Override failed.")
            st.exception(e)

# ------------- section 4: role inference -------------
st.header("4) Infer Developer vs Group (cluster by IDs)")
colR1, colR2 = st.columns([1, 3])
with colR1:
    infer_apply = st.checkbox("Apply to DB", value=True)
    infer_btn = st.button("Run role inference", type="primary")
if infer_btn:
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            infer_roles_run(state=state, apply=infer_apply)
        st.code(buf.getvalue() or "No output", language="text")
    except Exception as e:
        st.error("Role inference failed.")
        st.exception(e)

# -------------------- section 5: DB review -----------
st.header("5) DB review")
if not docs_df.empty:
    left, right = st.columns([2, 1])
    with right:
        status_filter = st.multiselect(
            "Filter status",
            ["accepted", "needs_review", "unassigned", "duplicate"],
            default=["accepted", "needs_review", "unassigned"],
        )
        search = st.text_input("Search filename contains", "")
    with left:
        df_view = docs_df.copy()
        if status_filter:
            df_view = df_view[df_view["status"].isin(status_filter)]
        if search:
            df_view = df_view[df_view["document_name"].str.contains(search, case=False, na=False)]
        st.dataframe(
            df_view.sort_values(by=["status", "confidence"], ascending=[True, False]),
            use_container_width=True,
            hide_index=True,
        )
else:
    st.info("DB table is empty. Upload or insert documents, then refresh.")
