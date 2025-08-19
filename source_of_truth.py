# # source_of_truth.py
# from __future__ import annotations
# from dataclasses import dataclass
# from typing import List, Optional, Dict, Iterable
# import json, os

# @dataclass(frozen=True)
# class Category:
#     slug: str
#     display: str
#     top_entity: str  # one of the 7
#     state_variant: Optional[str] = None  # TS|KA|None
#     org_variant: Optional[str] = None    # company|partnership|llp|None
#     keywords: List[str] = None
#     synonyms: List[str] = None
#     prototype: str = ""

# def load_sot(path: Optional[str] = None) -> List[Category]:
#     path = path or os.getenv("SOT_PATH", "source_of_truth_v1.json")
#     with open(path, "r", encoding="utf-8") as f:
#         data = json.load(f)
#     cats = []
#     for d in data:
#         cats.append(Category(
#             slug=d["slug"],
#             display=d["display"],
#             top_entity=d["top_entity"],
#             state_variant=d.get("state_variant"),
#             org_variant=d.get("org_variant"),
#             keywords=[k.lower() for k in d.get("keywords", [])],
#             synonyms=[s.lower() for s in d.get("synonyms", [])],
#             prototype=d.get("prototype", "")
#         ))
#     return cats

# def filter_by_state(cats: Iterable[Category], state: Optional[str]) -> List[Category]:
#     """Approvals & Land are state-specific; others are state-agnostic."""
#     state = (state or "").upper() or None
#     out: List[Category] = []
#     for c in cats:
#         if c.top_entity in ("project_approvals_documents", "project_land_documents"):
#             if state is None:
#                 continue
#             if c.state_variant == state:
#                 out.append(c)
#         else:
#             out.append(c)
#     return out

# def by_slug(cats: Iterable[Category]) -> Dict[str, Category]:
#     return {c.slug: c for c in cats}

# def names_for_fuzzy(c: Category) -> List[str]:
#     """Canonical names + synonyms for filename fuzzy match."""
#     base = [c.display, c.slug.replace("_", " ")]
#     syns = c.synonyms or []
#     return list({*(s.lower() for s in base), *syns})


# source_of_truth.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Iterable
import json, os

# --- helpers ---
_STATE_MAP = {
    # normalize to short codes your code comments mention
    "TELANGANA": "TS",
    "TS": "TS",
    "KARNATAKA": "KA",
    "KA": "KA",
}

def _norm_state(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().upper()
    return _STATE_MAP.get(s, v)   # fallback to original if unknown

def _first_org(org_types: Optional[List[str]]) -> Optional[str]:
    if not org_types:
        return None
    # keep single-org as a scalar, multi-org -> None (handled elsewhere/UI)
    uniq = [o.lower() for o in org_types if o]
    uniq = list(dict.fromkeys(uniq))
    return uniq[0] if len(uniq) == 1 else None

@dataclass(frozen=True)
class Category:
    slug: str
    display: str
    top_entity: str            # one of the 7
    state_variant: Optional[str] = None  # TS|KA|None
    org_variant: Optional[str] = None    # company|partnership|llp|None
    keywords: List[str] = None
    synonyms: List[str] = None
    prototype: str = ""

def load_sot(path: Optional[str] = None) -> List[Category]:
    """
    Load Source of Truth in either legacy (list) or new (dict with 'categories') form.
    Also maps new-field names -> your dataclass fields.
    """
    path = path or os.getenv("SOT_PATH", "source_of_truth_v1.json")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Accept both shapes
    if isinstance(raw, dict) and "categories" in raw:
        items = raw["categories"]           # new file shape
        new_shape = True
    elif isinstance(raw, list):
        items = raw                         # old file shape
        new_shape = False
    else:
        raise ValueError("Unrecognized SOT structure. Expected list or {categories:[...]}.")

    cats: List[Category] = []
    for d in items:
        # Map fields depending on shape
        if new_shape:
            slug = d["slug"]
            display = d.get("name") or d.get("display") or slug
            top_entity = d.get("entity_type") or d.get("top_entity") or ""
            state_variant = _norm_state(d.get("state"))
            org_variant = _first_org(d.get("org_types"))  # single org -> scalar; multi -> None
            keywords = [k.lower() for k in d.get("keywords", [])]
            synonyms = [s.lower() for s in d.get("synonyms", [])]
            prototype = d.get("prototype", "")
        else:
            slug = d["slug"]
            display = d["display"]
            top_entity = d["top_entity"]
            state_variant = _norm_state(d.get("state_variant"))
            org_variant = (d.get("org_variant") or None)
            keywords = [k.lower() for k in d.get("keywords", [])]
            synonyms = [s.lower() for s in d.get("synonyms", [])]
            prototype = d.get("prototype", "")

        cats.append(Category(
            slug=slug,
            display=display,
            top_entity=top_entity,
            state_variant=state_variant,
            org_variant=org_variant,
            keywords=keywords,
            synonyms=synonyms,
            prototype=prototype
        ))
    return cats

def filter_by_state(cats: Iterable[Category], state: Optional[str]) -> List[Category]:
    """Approvals & Land are state-specific; others are state-agnostic."""
    state = _norm_state(state)
    out: List[Category] = []
    for c in cats:
        if c.top_entity in ("project_approvals_documents", "project_land_documents"):
            if state is None:
                continue
            if c.state_variant == state:
                out.append(c)
        else:
            out.append(c)
    return out

def by_slug(cats: Iterable[Category]) -> Dict[str, Category]:
    return {c.slug: c for c in cats}

def names_for_fuzzy(c: Category) -> List[str]:
    """Canonical names + synonyms for filename fuzzy match."""
    base = [c.display, c.slug.replace("_", " ")]
    syns = c.synonyms or []
    return list({*(s.lower() for s in base), *syns})
