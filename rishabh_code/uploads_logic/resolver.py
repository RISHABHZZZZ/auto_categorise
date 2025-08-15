# resolver.py
from __future__ import annotations
import os, sys, argparse
from typing import List, Optional, Tuple, Dict
import numpy as np

from dotenv import load_dotenv
from source_of_truth import load_sot, filter_by_state, Category
from db import get_documents, get_chunks, update_match, filename_counts
from signals import (
    score_filename,
    score_keywords,
    doc_vector_mean,
    score_embeddings,
    is_generic_filename,
)
from fuse import fuse_scores
from rules import rules_from_text_and_filename   # <<< new, see rules.py below


# -------- optional local embedder for category prototypes (S3) --------
_MODEL = None
def get_embedder():
    """Lazily load sentence-transformers to embed category prototypes.
       If unavailable, we continue with S3=0 and rely on rules/s1/s2."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return _MODEL
    except Exception as e:
        print("Note: sentence-transformers unavailable; embedding score (S3) will be 0.", file=sys.stderr)
        return None


def build_category_vectors(cats: List[Category]) -> Dict[str, np.ndarray]:
    """Encode each category's prototype text (display + keywords + prototype) to a vector."""
    model = get_embedder()
    if model is None:
        return {}
    texts, slugs = [], []
    for c in cats:
        blob = " | ".join([
            c.display,
            " ".join(c.keywords or []),
            c.prototype or ""
        ])
        slugs.append(c.slug)
        texts.append(blob)
    mat = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return {slug: mat[i] for i, slug in enumerate(slugs)}


def categorize_document(
    doc_row: Dict,
    cats: List[Category],
    cat_vecs: Dict[str, np.ndarray],
    fname_cnts: Dict[str, int],
    state_variant: Optional[str] = None,
    topk_show: int = 3
) -> Dict:
    """Score one document against candidate categories and return decision + debug info."""
    doc_id = doc_row["id"]
    fname  = doc_row["document_name"]
    fname_l = fname.lower()

    # Load content/embeddings
    chunks = get_chunks(doc_id)                      # [(chunk_id, text, emb), ...]
    doc_vec = doc_vector_mean(chunks, max_chunks=8)  # 384-d or None

    # Build a larger text window for rules (first ~20k chars or first 12 chunks)
    texts = []
    for _, ch_text, _ in chunks[:12]:
        texts.append(ch_text)
        if sum(len(t) for t in texts) > 20000:
            break
    full_text = "\n".join(texts)

    # 1) High-precision rules over content + filename hints
    # returns list[(slug, score(0.8-0.95), reason)], already state-aware
    rule_hits = rules_from_text_and_filename(full_text, fname, state_variant)
    rule_best = max(rule_hits, key=lambda x: x[1]) if rule_hits else None

    # 2) Dynamic fusion weights: reduce filename weight if duplicated/generic
    # base weights: (s1, s2, s3) ~= (0.40, 0.30, 0.30)


    # is_dup   = fname_cnts.get(fname_l, 0) > 1
    # dup_factor = 0.4 if is_dup else 1.0
    # gen_factor = 0.4 if is_generic_filename(fname) else 1.0
    # w_s1 = 0.40 * dup_factor * gen_factor
    # weights = (w_s1, 0.30, 0.30)
    dup_count = fname_cnts.get(fname_l, 0)
    generic = is_generic_filename(fname)

    if generic or dup_count >= 3:
        w_s1 = 0.0               # totally ignore filename when it's junky
    elif dup_count == 2:
        w_s1 = 0.20              # light touch
    else:
        w_s1 = 0.40              # full weight when unique & meaningful

    weights = (w_s1, 0.30, 0.30)

    # 3) Score each category using s1/s2/s3 and fuse
    scored: List[Tuple[str, float, Tuple[float,float,float], Category]] = []
    for c in cats:
        s1 = score_filename(fname, c)
        s2 = score_keywords(chunks, c, top_k=6)  # a little wider
        s3 = score_embeddings(doc_vec, cat_vecs.get(c.slug))
        final = fuse_scores(s1, s2, s3, w=weights)
        scored.append((c.slug, final, (s1, s2, s3), c))
    scored.sort(key=lambda x: x[1], reverse=True)

    # Best fused candidate
    slug, final, (s1, s2, s3), cat = scored[0]

    # 4) If a strong rule hit exists, let it override/boost (rules are authoritative)
    rule_applied = None
    if rule_best:
        r_slug, r_score, reason = rule_best
        # If the rule's slug exists in our candidate list (state-filtered), force it on top
        found = False
        for (_slug, _final, _parts, _cat) in scored:
            if _slug == r_slug:
                slug = r_slug
                cat  = _cat
                final = max(final, r_score)   # rules carry high confidence
                found = True
                rule_applied = {"slug": r_slug, "score": round(r_score,3), "reason": reason}
                break
        if not found:
            # If rule's slug not in filtered candidates (e.g., wrong state),
            # still allow a boost but not a full override.
            final = max(final, r_score * 0.9)
            rule_applied = {"slug": r_slug, "score": round(r_score*0.9,3), "reason": reason + " (partial)"}

    # 5) Thresholds (as agreed)
    if final >= 0.70:
        status = "accepted"
    elif final >= 0.60:
        status = "needs_review"
    else:
        status = "unassigned"

    # Top-K preview
    preview = [{
        "rank": i+1,
        "slug": rec[0],
        "score": round(rec[1], 3),
        "s1_fn": round(rec[2][0], 3),
        "s2_kw": round(rec[2][1], 3),
        "s3_emb": round(rec[2][2], 3),
        "display": rec[3].display,
        "top_entity": rec[3].top_entity,
        "state_variant": rec[3].state_variant,
        "org_variant": rec[3].org_variant,
    } for i, rec in enumerate(scored[:topk_show])]

    return {
        "doc_id": doc_id,
        "document_name": fname,
        "best_slug": slug,
        "best_display": cat.display,
        "top_entity": cat.top_entity,
        "state_variant": cat.state_variant,
        "org_variant": cat.org_variant,
        "final": round(final, 3),
        "s1": round(s1, 3), "s2": round(s2, 3), "s3": round(s3, 3),
        "status": status,
        "topk": preview,
        "rule": rule_applied,
        "weights": {"s1": round(weights[0],2), "s2": round(weights[1],2), "s3": round(weights[2],2)},
        "is_dup_name": (dup_count >= 2),
        "name_dup_count": dup_count,
        "is_generic_name": is_generic_filename(fname),
    }


def run(state: str, limit: Optional[int], apply: bool) -> None:
    load_dotenv()

    # SoT & candidates
    all_cats = load_sot()
    cats = filter_by_state(all_cats, state)
    cat_vecs = build_category_vectors(cats)  # may be empty if embedder not installed

    # Filename duplication table (for filename weight dampening)
    fname_cnts = filename_counts()

    docs = get_documents(limit=limit)
    results = []
    for row in docs:
        res = categorize_document(row, cats, cat_vecs, fname_cnts, state_variant=state)
        results.append(res)

        # Console preview
        rule_tag = ""
        if res["rule"]:
            rule_tag = f"  (rule:{res['rule']['slug']} {res['rule']['score']})"
        print(f"\n[{res['status']}] #{res['doc_id']} {res['document_name']} -> "
              f"{res['best_display']} ({res['best_slug']}) score={res['final']}  "
              f"s1={res['s1']} s2={res['s2']} s3={res['s3']}  "
              f"w={res['weights']}{rule_tag}")

        for tk in res["topk"]:
            print(f"  - {tk['rank']}. {tk['display']} [{tk['slug']}] => {tk['score']} "
                  f"(fn {tk['s1_fn']}, kw {tk['s2_kw']}, emb {tk['s3_emb']})")

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

    print(f"\nDone. {'Applied to DB' if apply else 'Dry run only'} for {len(results)} docs.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=os.getenv("STATE_DEFAULT", "TS"), help="TS or KA")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--apply", action="store_true", help="Write results back to DB")
    args = ap.parse_args()
    run(args.state.upper(), args.limit, args.apply)
