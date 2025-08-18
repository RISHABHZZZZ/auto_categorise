# entity_role_infer.py
from __future__ import annotations
import re, argparse
from typing import Dict, List, Tuple, Optional
from collections import defaultdict, Counter

from db import get_documents, get_chunks, update_match
from rules import PAN_RX, GSTIN_RX, CIN_RX, LLPIN_RX

# --- name extraction & normalization ---
NAME_RX = re.compile(r"(?:Name|Legal Name|Name of (?:Business|Company)|Account Name)\s*[:\-]\s*([A-Z0-9&.,() /\-]+)", re.I)

def norm_name(s: str) -> str:
    s = s.upper()
    for token in [" PRIVATE LIMITED", " PVT LTD", " LTD", " LIMITED", " LLP", " PARTNERSHIP FIRM", " FIRM", " COMPANY"]:
        s = s.replace(token, "")
    s = re.sub(r"[^A-Z0-9& ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# --- pull identifiers out of early text ---
def extract_facts(text: str) -> Dict[str,str]:
    facts: Dict[str,str] = {}
    if m := PAN_RX.search(text):    facts["pan"] = m.group(0)
    if m := GSTIN_RX.search(text):  facts["gstin"] = m.group(0)
    if m := CIN_RX.search(text):    facts["cin"] = m.group(0)
    if m := LLPIN_RX.search(text):  facts["llpin"] = m.group(0)
    if m := NAME_RX.search(text):   facts["name"] = m.group(1).strip()
    # derive PAN from GSTIN (chars 3..12)
    if "gstin" in facts and "pan" not in facts and len(facts["gstin"]) >= 12:
        facts["pan"] = facts["gstin"][2:12]
    if "name" in facts:
        facts["name_key"] = norm_name(facts["name"])
    return facts

def entity_key(f: Dict[str,str]) -> Optional[str]:
    for k in ("pan","gstin","llpin","cin","name_key"):  # strongest first
        if k in f and f[k]:
            return f"{k}:{f[k]}"
    return None

# --- features we score to decide Developer vs Group ---
DEV_STRONG = {"tan","msme","lei","sanction_soa","cibil","bank_stmt_entity"}
DEV_COMMON = {"gst_pan","financials_3y","itrs_3y","coi_moa_aoa","partnership_deed","llp_agreement"}

def feature_from_slug(slug: str) -> Optional[str]:
    s = (slug or "").lower()
    if "tan" in s: return "tan"
    if "msme" in s: return "msme"
    if "lei" in s: return "lei"
    if "sanction" in s or "soa" in s: return "sanction_soa"
    if "cibil" in s: return "cibil"
    if "bank_stmt" in s and "directors" not in s: return "bank_stmt_entity"
    if "gst_pan" in s: return "gst_pan"
    if "financial" in s: return "financials_3y"
    if "itrs" in s: return "itrs_3y"
    if "moa_aoa" in s or "incorp" in s: return "coi_moa_aoa"
    if "partnership_deed" in s: return "partnership_deed"
    if "llp_agreement" in s: return "llp_agreement"
    return None

def org_variant_from_slugs(slugs: List[str]) -> str:
    s = " ".join(slugs)
    if "llp_agreement" in s or " llp " in s: return "llp"
    if "partnership_deed" in s or "partnership" in s: return "partnership"
    if "moa_aoa" in s or "incorp" in s or "coi" in s: return "company"
    return "company"  # default

def score_role(features: Counter) -> Tuple[int,int]:
    dev = 0
    for f, c in features.items():
        if f in DEV_STRONG: dev += 2*c
        elif f in DEV_COMMON: dev += 1*c
    group = sum(c for f,c in features.items() if f in DEV_COMMON)
    return dev, group

def run(state: str, apply: bool):
    # pull all docs (already categorized by resolver.py ideally)
    docs = get_documents()
    doc_info = []
    for row in docs:
        # take a small text window
        chunks = get_chunks(row["id"])[:3]
        text = "\n".join(ch[1] for ch in chunks)
        facts = extract_facts(text)
        key = entity_key(facts)
        slug = (row.get("canonical_slug") or "").lower()
        doc_info.append((row, key, facts, slug))

    # cluster by entity key
    clusters: Dict[str, Dict] = {}
    for row, key, facts, slug in doc_info:
        if not key:  # skip docs we can't tie to an entity
            continue
        c = clusters.setdefault(key, {"docs":[], "slugs":[], "features":Counter(), "facts":facts})
        c["docs"].append(row)
        c["slugs"].append(slug)
        if (f := feature_from_slug(slug)): c["features"][f] += 1

    if not clusters:
        print("No identifiable entities by PAN/GSTIN/LLPIN/CIN; nothing to assign.")
        return

    # compute scores and pick roles
    scored = []
    for key, c in clusters.items():
        variant = org_variant_from_slugs(c["slugs"])
        dev_score, group_score = score_role(c["features"])
        scored.append((key, dev_score, group_score, variant, c))
    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)

    dev_key = scored[0][0]
    grp_key = scored[1][0] if len(scored) > 1 else dev_key

    # write back role + variant
    for key, dev_score, group_score, variant, c in scored:
        role = "developer_entity" if key == dev_key else ("group_entity" if key == grp_key else "other_entity")
        for row in c["docs"]:
            update_match(
                row["id"],
                slug=row.get("canonical_slug"),
                top_entity=role,
                org_variant=variant,
                state_variant=row.get("state_variant"),
                confidence=row.get("confidence"),
                status=row.get("status") or "unassigned",
            )
        print(f"[{role}] entity={key} variant={variant} features={dict(c['features'])} dev={dev_score} grp={group_score}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="TS")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    run(args.state.upper(), args.apply)
