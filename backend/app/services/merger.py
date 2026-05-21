"""Merge PDF + Excel extraction JSONs into a single payload for XBRL generation.

Rules (per design):
- Numeric fields:  Excel wins if present & non-zero, else PDF.
- Text/narrative:  PDF wins, else Excel.
- Identity fields: PDF wins, else Excel.
- Array fields:    Excel wins, else PDF.

Conflicts (numeric values differing by > 0.5% AND > 1000) are logged into
``_conflicts`` for downstream debugging. ``_provenance`` records which source
each leaf came from.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Field-name hints to detect category when type alone isn't enough.
IDENTITY_KEYS = {
    "cin", "pan", "firm_name", "frn", "membership_number", "udin", "din",
    "place", "registered_office", "auditor_address", "company_name",
}
NARRATIVE_KEYS = {
    "opinion_type", "opinion_text", "key_audit_matters", "basis_of_opinion",
    "going_concern_note", "significant_accounting_policies",
    "contingent_liabilities_note", "csr_narrative", "auditor_opinion",
    "directors_report", "carro_disclosures",
}


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        s = value.strip()
        return s == "" or s.upper() == "FILL VALUE HERE" or s == "—"
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    return False


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _significant_conflict(a: float, b: float) -> bool:
    if abs(a - b) <= 1000:
        return False
    larger = max(abs(a), abs(b))
    if larger == 0:
        return False
    return (abs(a - b) / larger) > 0.005


def merge_extractions(
    pdf_data: dict, xlsx_data: dict
) -> tuple[dict, dict, list[dict]]:
    """Merge two extraction JSONs.

    Returns (merged_data, provenance, conflicts).
    """
    provenance: dict[str, str] = {}
    conflicts: list[dict] = []
    merged = _merge(pdf_data, xlsx_data, "", provenance, conflicts)
    return merged, provenance, conflicts


def _merge(
    pdf_val: Any,
    xlsx_val: Any,
    path: str,
    provenance: dict[str, str],
    conflicts: list[dict],
) -> Any:
    pdf_empty = _is_empty(pdf_val)
    xlsx_empty = _is_empty(xlsx_val)

    # Both empty
    if pdf_empty and xlsx_empty:
        if pdf_val is not None:
            return pdf_val
        return xlsx_val

    # Only one source has a value
    if pdf_empty:
        provenance[path] = "xlsx"
        return xlsx_val
    if xlsx_empty:
        provenance[path] = "pdf"
        return pdf_val

    # Both present — recurse for dicts
    if isinstance(pdf_val, dict) and isinstance(xlsx_val, dict):
        out: dict = {}
        for key in set(pdf_val.keys()) | set(xlsx_val.keys()):
            child_path = f"{path}.{key}" if path else key
            out[key] = _merge(
                pdf_val.get(key), xlsx_val.get(key), child_path, provenance, conflicts
            )
        return out

    # Both present — arrays: prefer xlsx (more structured) unless empty
    if isinstance(pdf_val, list) and isinstance(xlsx_val, list):
        if len(xlsx_val) >= len(pdf_val):
            provenance[path] = "xlsx"
            return xlsx_val
        provenance[path] = "pdf"
        return pdf_val

    # Mixed types — prefer non-empty xlsx as it's more structured for CA data
    if isinstance(pdf_val, list) or isinstance(xlsx_val, list):
        provenance[path] = "xlsx" if isinstance(xlsx_val, list) else "pdf"
        return xlsx_val if isinstance(xlsx_val, list) else pdf_val

    # Both scalars
    leaf_name = path.rsplit(".", 1)[-1].lower()
    is_identity = leaf_name in IDENTITY_KEYS
    is_narrative = leaf_name in NARRATIVE_KEYS or (
        isinstance(pdf_val, str) and len(pdf_val) > 40
    )

    if _is_numeric(pdf_val) and _is_numeric(xlsx_val):
        if pdf_val != xlsx_val and _significant_conflict(float(pdf_val), float(xlsx_val)):
            conflicts.append({
                "path": path,
                "pdf": pdf_val,
                "xlsx": xlsx_val,
                "diff": float(xlsx_val) - float(pdf_val),
            })
        # Excel wins for numbers
        provenance[path] = "xlsx"
        return xlsx_val

    if is_identity or is_narrative:
        provenance[path] = "pdf"
        return pdf_val

    # Default for text/scalar where both present: prefer PDF (audited source)
    provenance[path] = "pdf"
    return pdf_val
