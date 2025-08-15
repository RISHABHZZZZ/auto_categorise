# source_of_truth.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Iterable
import json, os

@dataclass(frozen=True)
class Category:
    slug: str
    display: str
    top_entity: str  # one of the 7
    state_variant: Optional[str] = None  # TS|KA|None
    org_variant: Optional[str] = None    # company|partnership|llp|None
    keywords: List[str] = None
    synonyms: List[str] = None
    prototype: str = ""

def load_sot(path: Optional[str] = None) -> List[Category]:
    path = path or os.getenv("SOT_PATH", "source_of_truth_v1.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cats = []
    for d in data:
        cats.append(Category(
            slug=d["slug"],
            display=d["display"],
            top_entity=d["top_entity"],
            state_variant=d.get("state_variant"),
            org_variant=d.get("org_variant"),
            keywords=[k.lower() for k in d.get("keywords", [])],
            synonyms=[s.lower() for s in d.get("synonyms", [])],
            prototype=d.get("prototype", "")
        ))
    return cats

def filter_by_state(cats: Iterable[Category], state: Optional[str]) -> List[Category]:
    """Approvals & Land are state-specific; others are state-agnostic."""
    state = (state or "").upper() or None
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
