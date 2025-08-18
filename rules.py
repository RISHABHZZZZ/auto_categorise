# rules.py
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import re

def _rx(p:str, flags=re.I|re.M): return re.compile(p, flags)

# --- Strong IDs / Corporate markers ---
PAN_RX   = _rx(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
TAN_RX   = _rx(r"\b[A-Z]{4}[0-9]{5}[A-Z]\b")
GSTIN_RX = _rx(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
LEI_RX   = _rx(r"\b(?:Legal\s+Entity\s+Identifier|LEI)\b.*?\b([A-Z0-9]{20})\b", re.I|re.S)

CIN_RX   = _rx(r"\b[UL]\d{2}[A-Z]{3}\d{4}[A-Z]{3}\d{6}\b")
LLPIN_RX = _rx(r"\bLLPIN\b[:\s-]*[A-Z]{3}-?\d{4}\b")
COI_RX   = _rx(r"\bCertificate\s+of\s+Incorporation\b|\bCOI\b")
MOA_RX   = _rx(r"\bMemorandum\s+of\s+Association\b|\bMOA\b")
AOA_RX   = _rx(r"\bArticles\s+of\s+Association\b|\bAOA\b")

COMPANY_MARKERS_RX = _rx(r"\b(Pvt\.?|Private)\s+Limited\b|\bLLP\b|\bLLPIN\b|\bCIN\b|\bCompany\b|\bInc\b|\bLtd\b")

# --- Approvals & infra ---
RERA_RX  = _rx(r"\bRERA\b|\bTSRERA\b|\bK-?RERA\b")
HMDA_RX  = _rx(r"\bHyderabad\s+Metropolitan\s+Development\s+Authority\b|\bHMDA\b")
DC_RX    = _rx(r"\bDevelopment\s+Permission\b|\bDC\s+Letter\b|\bBuilding\s+Permission\b")
BPO_RX   = _rx(r"\bBuilding\s+Permit\s+Order\b|\bPermit\s+Order\b")
FIRE_RX  = _rx(r"\b(Provisional\s+)?No\s*Objection\s*Certificate\b.*\bFire\b")
PCB_RX   = _rx(r"\bPollution\s+Control\s+Board\b|\bConsent\s+to\s+(Establish|Operate)\b|\bCTE\b|\bCTO\b")
AAI_RX   = _rx(r"\bAirports?\s+Authority\s+of\s+India\b|\bAAI\b.*\bNOC\b|\bheight\s+clearance\b")

BWSSB_RX = _rx(r"\bBWSSB\b|\bWater\s+Supply\b|\bWater\s+Connection\b")
HMWS_RX  = _rx(r"\bHMWS&SB\b|\bHyderabad\s+Metropolitan\s+Water\b")
BESCOM_RX= _rx(r"\bBESCOM\b|\bBangalore\s+Electricity\b")
BSNL_RX  = _rx(r"\bBharat\s+Sanchar\s+Nigam\s+Limited\b|\bBSNL\b")

# --- Legal / Land ---
EC_RX    = _rx(r"\bEncumbrance\s+Certificate\b|\bForm\s+1[56]\b")
PAHANI_RX= _rx(r"\bPahani\b|\b1B\b|\bROR\b|\bAdangal\b")
PASSBOOK_RX=_rx(r"\bPassbook\b")

DAGPA_RX = _rx(r"\bDevelopment\s+Agreement[-\s]*cum\s+GPA\b|\bDAGPA\b")
JDA_RX   = _rx(r"\bJoint\s+Development\s+Agreement\b|\bJDA\b")
GPA_RX   = _rx(r"\bGeneral\s+Power\s+of\s+Attorney\b|\bGPA\b")
NALA_RX  = _rx(r"\bNALA\b|\bNon-?Agricultural\s+Land\s+Assessment\b")
LUC_RX   = _rx(r"\bLand\s+Use\s+Certificate\b|\bLUC\b")
TDR_RX   = _rx(r"\bTransfer\s+of\s+Development\s+Rights\b|\bTDR\b")

# --- Bank statement detection ---
BANK_STMT_RX      = _rx(r"\b(Account\s+Statement|Statement\s+of\s+Account|SOA|Account\s+No\.?|A/c\s+No\.?|IFSC)\b")
CORP_HINTS_RX     = COMPANY_MARKERS_RX

# slug -> regex list (text-based rules; high precision)
TEXT_RULES = {
    # IDs / KYC
    "directors_pan_aadhaar": [PAN_RX, _rx(r"\bAadhaar\b")],
    "dev_company_gst_pan":   [GSTIN_RX],
    "dev_company_tan":       [TAN_RX],
    "dev_company_lei":       [LEI_RX],

    # Company / Incorporation
    "dev_company_moa_aoa_incorp": [MOA_RX, AOA_RX],
    "group_company_moa_aoa_incorp":[MOA_RX, AOA_RX],
    "dev_llp_agreement_incorp": [LLPIN_RX, COI_RX],   # LLP + COI
    "dev_partnership_deed_registration": [_rx(r"\bPartnership\s+Deed\b|\bFirm\s+Registration\b")],

    # Approvals (TS)
    "ts_hmda_dc_letter": [HMDA_RX, DC_RX],
    "ts_building_permit_order": [BPO_RX],
    "ts_provisional_fire_noc": [FIRE_RX],
    "ts_pollution_noc": [PCB_RX],
    "ts_airport_authority": [AAI_RX],
    "ts_rera_certificate": [RERA_RX],
    "ts_permission_water_supply": [HMWS_RX],

    # Approvals (KA)
    "ka_commencement_letter": [_rx(r"\bCommencement\s+(Certificate|Letter)\b")],
    "ka_provisional_fire_noc": [FIRE_RX],
    "ka_pollution_noc": [PCB_RX],
    "ka_airport_authority": [AAI_RX],
    "ka_rera": [RERA_RX],
    "ka_permission_water_supply": [BWSSB_RX],
    "ka_bescom": [BESCOM_RX],
    "ka_bsnl": [BSNL_RX],

    # Legal
    "legal_certified_ec": [EC_RX],
    "legal_pahanies":     [PAHANI_RX],
    "legal_passbooks":    [PASSBOOK_RX],

    # Land
    "land_ts_dagpa": [DAGPA_RX],
    "land_ka_jda":   [JDA_RX],
    "land_ka_gpa":   [GPA_RX],
    "land_ts_nala":  [NALA_RX],
    "land_ts_land_use_certificate": [LUC_RX],
    "land_ts_tdr":   [TDR_RX],
    "land_ka_tdr":   [TDR_RX],
}

# filename tokens -> candidate slugs (both states where applicable; resolver filters by state)
FILENAME_HINTS = {
    "gst":  ["dev_company_gst_pan","group_company_gst_pan","dev_llp_gst_pan","dev_partnership_gst_pan"],
    "tan":  ["dev_company_tan","dev_llp_tan","dev_partnership_tan"],
    "lei":  ["dev_company_lei","dev_llp_lei","dev_partnership_lei"],
    "rera": ["ts_rera_certificate","ka_rera"],
    "hmda": ["ts_hmda_dc_letter"],
    "aai":  ["ts_airport_authority","ka_airport_authority"],
    "moa":  ["dev_company_moa_aoa_incorp","group_company_moa_aoa_incorp"],
    "aoa":  ["dev_company_moa_aoa_incorp","group_company_moa_aoa_incorp"],
    "coi":  ["dev_llp_agreement_incorp"],   # rough, still helps
    "accountstatement": ["dev_company_bank_stmt","dev_llp_bank_stmt","dev_partnership_bank_stmt","directors_bank_stmt_1y"],
    "statement":        ["dev_company_bank_stmt","dev_llp_bank_stmt","dev_partnership_bank_stmt","directors_bank_stmt_1y"],
}

def _add_hit(hits: List[Tuple[str,float,str]], slug:str, score:float, why:str):
    hits.append((slug, min(0.95, score), why))

def _bank_router(text: str, state: Optional[str]) -> List[Tuple[str,float,str]]:
    out: List[Tuple[str,float,str]] = []
    if not BANK_STMT_RX.search(text):
        return out
    # If clear corporate hints -> entity statements
    if CORP_HINTS_RX.search(text) or GSTIN_RX.search(text) or CIN_RX.search(text) or LLPIN_RX.search(text):
        for s in ("dev_company_bank_stmt","dev_llp_bank_stmt","dev_partnership_bank_stmt"):
            _add_hit(out, s, 0.9, "bank statement + corporate markers")
    else:
        _add_hit(out, "directors_bank_stmt_1y", 0.9, "bank statement + no corporate markers")
    return out

def rules_from_text_and_filename(text: str, filename: str, state: Optional[str]) -> List[Tuple[str,float,str]]:
    hits: List[Tuple[str,float,str]] = []

    # 1) text rules (high precision)
    for slug, regs in TEXT_RULES.items():
        local = 0.0
        reasons = []
        for r in regs:
            if r.search(text):
                local += 0.5 if local == 0.0 else 0.25  # diminishing returns
                reasons.append(r.pattern[:48] + ("..." if len(r.pattern) > 48 else ""))
        if local >= 0.8:
            _add_hit(hits, slug, local, "; ".join(reasons))

    # 2) bank statement router (text-based)
    hits.extend(_bank_router(text, state))

    # 3) filename hard hints (distinctive tokens)
    base = filename.lower()
    base = re.sub(r"\.(pdf|png|jpg|jpeg|tif|tiff|docx?)$", "", base)
    tokenmap = {
        "gst":"gst", "tan":"tan", "lei":"lei", "rera":"rera", "hmda":"hmda", "aai":"aai",
        "moa":"moa", "aoa":"aoa", "coi":"coi",
        "accountstatement":"accountstatement", "statement":"statement"
    }
    for token, key in tokenmap.items():
        if token in base:
            for slug in FILENAME_HINTS.get(key, []):
                _add_hit(hits, slug, 0.85, f"filename:{token}")

    # 4) state filter for returned hits (resolver already filters cats;
    #     but filename hints may include both states; we'll let resolver handle it)
    return hits
