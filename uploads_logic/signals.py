# signals.py
from __future__ import annotations
from typing import List, Tuple, Optional
from dataclasses import dataclass
from rapidfuzz import fuzz
import numpy as np
import re

from source_of_truth import Category, names_for_fuzzy

_WORD = re.compile(r"[A-Za-z0-9]+")

def _norm01(x: float, lo: float, hi: float) -> float:
    if hi <= lo: return 0.0
    x = max(lo, min(hi, x))
    return (x - lo) / (hi - lo)

def score_filename(file_name: str, cat: Category) -> float:
    """0–1 based on fuzzy match between filename and cat names/synonyms."""
    base = file_name.rsplit("/", 1)[-1].lower()
    base = re.sub(r"\.(pdf|png|jpg|jpeg|tif|tiff|docx?)$", "", base)
    best = 0
    for cand in names_for_fuzzy(cat):
        # try a few complementary metrics and keep the best
        s1 = fuzz.token_set_ratio(base, cand)
        s2 = fuzz.partial_ratio(base, cand)
        s3 = fuzz.QRatio(base, cand)
        best = max(best, s1, s2, s3)
    return best / 100.0

def score_keywords(chunks: List[Tuple[int, str, list]], cat: Category, top_k: int = 3) -> float:
    """0–1 based on presence of keywords/synonyms in the first few chunks."""
    kws = (cat.keywords or []) + (cat.synonyms or [])
    if not kws:
        return 0.0
    text = " ".join(ch[1] for ch in chunks[:top_k]).lower()
    hits = 0
    for kw in kws:
        if not kw: 
            continue
        # loose contains; if kw has multiple words, this still works
        if kw.lower() in text:
            hits += 1
    # proportion of keywords that hit; dampen to avoid overpowering filename
    prop = hits / max(1, len(kws))
    return _norm01(prop, 0.0, 0.6)  # cap modestly

def doc_vector_mean(chunks, max_chunks: int = 8):
    vecs = []
    for _, _, emb in chunks[:max_chunks]:
        if emb is None:
            continue
        if isinstance(emb, np.ndarray):
            if emb.size == 0:
                continue
            v = emb.astype(np.float32, copy=False)
        elif isinstance(emb, (list, tuple)):
            if len(emb) == 0:
                continue
            v = np.asarray(emb, dtype=np.float32)
        else:
            # Unknown type (string/bytes/etc.) — skip
            continue
        vecs.append(v)
    return np.mean(vecs, axis=0) if vecs else None

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0: 
        return 0.0
    return float(np.dot(a, b) / denom)

@dataclass(frozen=True)
class ProtoVec:
    slug: str
    vec: np.ndarray

def score_embeddings(doc_vec: Optional[np.ndarray], cat_vec: Optional[np.ndarray]) -> float:
    """0–1 cosine; returns 0 if we don't have vectors."""
    if doc_vec is None or cat_vec is None:
        return 0.0
    return _norm01(cosine(doc_vec, cat_vec), 0.2, 0.9)  # squash to 0–1 with gentle floor/ceiling


# signals.py (add)
GENERIC_TOKENS = {"scan","scanned","document","doc","file","new","untitled","image","img","photo"}
def is_generic_filename(name: str) -> bool:
    base = name.rsplit("/",1)[-1].lower()
    base = re.sub(r"\.(pdf|png|jpg|jpeg|tif|tiff|docx?)$", "", base)
    toks = set(_WORD.findall(base))
    if not toks: return True
    if toks & GENERIC_TOKENS: return True
    if len(base) <= 6: return True
    # mostly digits/underscores?
    digits = sum(ch.isdigit() for ch in base)
    if digits / max(1,len(base)) > 0.6: return True
    return False