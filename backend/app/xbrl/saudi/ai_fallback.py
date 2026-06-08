"""AI-assisted fallback for the Saudi-IFRS source mapper.

After source_mapper.map_concepts() runs the pure Python direct/synonym
lookup, some concepts remain status="missing". This module makes a SINGLE
batched Gemini call that:

  - Sees every still-unresolved concept (business_term + xbrl_tag)
  - Sees every candidate row from the PDF's primary-statement tables that
    the Python pass did NOT consume
  - Returns one mapping per concept: the best matching line_item, the row
    values, and a confidence score.

This handles:
  - English synonyms not in the YAML
  - Arabic line items (no synonyms needed in the YAML)
  - Semantic matches the direct lookup couldn't make
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Optional

from app.services.extractor import query_gemini_text
from app.xbrl.saudi.source_mapper import (
    NON_TAG_VALUES,
    ResolvedFact,
    ResolvedFactSet,
    SECTION_TITLE_HINTS,
    _classify_year_columns,
    _is_year_column,
    _normalize,
)
from app.xbrl.saudi.taxonomy_loader import Taxonomy


# Sections we let the AI search; metadata/SOCPA text concepts stay rule-driven.
TABLE_SECTIONS = {"balance_sheet", "income_statement", "cash_flow", "changes_in_equity"}


def _section_label(section_id: str) -> str:
    return {
        "balance_sheet": "Balance Sheet",
        "income_statement": "Income Statement (P&L)",
        "cash_flow": "Cash Flow Statement",
        "changes_in_equity": "Statement of Changes in Equity",
    }.get(section_id, section_id)


def _collect_candidate_rows(
    tables_json: dict, resolved_evidence: set[tuple[int, str]],
) -> list[dict]:
    """Collect every row from primary statements that the direct pass didn't
    already attach to a concept.

    Each candidate carries enough info for Gemini to map it:
      row_id, table_section, page, line_item, columns:{header:value}
    """
    candidates: list[dict] = []
    for table_idx, table in enumerate(tables_json.get("tables", [])):
        if not table.get("found"):
            continue
        title = (table.get("title_as_printed") or table.get("target_title") or "").lower()
        # Determine which section this table belongs to (best effort)
        section_for_table = None
        for sid, hints in SECTION_TITLE_HINTS.items():
            if any(h in title for h in hints):
                section_for_table = sid
                break
        if section_for_table is None:
            continue   # we only consider primary statements
        columns = table.get("columns") or []
        year_cols = [c for c in columns if _is_year_column(c)]
        cy_col, py_col = _classify_year_columns(year_cols)
        for row_idx, row in enumerate(table.get("rows") or []):
            li = row.get("line_item") or row.get("description")
            if not li or not isinstance(li, str):
                continue
            li = li.strip()
            if not li:
                continue
            # Skip rows that direct lookup already consumed (table_idx + line_item)
            if (table_idx, _normalize(li)) in resolved_evidence:
                continue
            cy_val = row.get(cy_col) if cy_col else None
            py_val = row.get(py_col) if py_col else None
            # Skip pure section header rows (both year vals null)
            if cy_val is None and py_val is None:
                continue
            candidates.append({
                "row_id": f"t{table_idx}r{row_idx}",
                "section": section_for_table,
                "page": table.get("page"),
                "line_item": li,
                "cy_col": cy_col,
                "py_col": py_col,
                "value_cy": cy_val,
                "value_py": py_val,
                "currency": table.get("currency"),
            })
    return candidates


def _build_prompt(
    missing: list[ResolvedFact],
    candidates: list[dict],
) -> str:
    concepts_block = "\n".join(
        f"- id: {f.business_term} | section: {_section_label(f.section_id)} | tag: {f.xbrl_tag}"
        for f in missing
    )

    rows_block_lines = []
    for c in candidates:
        cy = c["value_cy"] if c["value_cy"] is not None else "—"
        py = c["value_py"] if c["value_py"] is not None else "—"
        rows_block_lines.append(
            f"  {c['row_id']}  [{_section_label(c['section'])}]  p.{c['page']}  "
            f"\"{c['line_item']}\"  CY={cy}  PY={py}"
        )
    rows_block = "\n".join(rows_block_lines)

    return f"""You are matching IFRS XBRL concepts to actual line items from a
Saudi listed company's annual report.

Each IFRS CONCEPT below needs to be matched to ONE candidate ROW from the
PDF (or to null when nothing applies).

Match rules:
  - Match by MEANING, not literal text.
  - For Arabic line items, translate mentally:
      الإيرادات / المبيعات              → Revenue
      تكلفة الإيرادات / تكلفة المبيعات   → Cost of Sales
      ربح إجمالي                        → Gross Profit
      إجمالي الأصول                     → Total Assets
      إجمالي الإلتزامات                 → Total Liabilities
      إجمالي حقوق الملكية                → Total Equity
      صافي الربح / صافي ربح السنة        → Profit for the Year
      الزكاة / الزكاة والضرائب           → Zakat Expense
      الممتلكات والمعدات                → Property Plant Equipment
      النقد وما في حكمه                  → Cash & Cash Equivalents
      ذمم مدينة                         → Trade Receivables
      ذمم دائنة                         → Trade Payables
  - The candidate row's "section" tells you which primary statement it came
    from — prefer rows whose section matches the concept's section.
  - Each row may be used by AT MOST ONE concept.
  - If no row from the candidates is a genuine semantic match for a
    concept, return match=null for that concept. NEVER force a match.

IFRS CONCEPTS TO RESOLVE:
{concepts_block}

CANDIDATE ROWS (line items not yet consumed):
{rows_block}

OUTPUT — JSON ONLY, no markdown:
{{
  "mappings": [
    {{
      "concept_id": "<business_term from list above>",
      "row_id": "<row_id from candidates>" or null,
      "confidence": "high" | "medium" | "low",
      "reason": "<one short sentence>"
    }}
  ]
}}

Every concept must appear exactly once in mappings.
"""


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.replace("```json", "").replace("```JSON", "").rstrip("`").strip()
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        text = text[first:last + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


def _existing_evidence_keys(facts: ResolvedFactSet, tables_json: dict) -> set[tuple[int, str]]:
    """Find which (table_idx, normalized_line_item) pairs were used by the
    direct/synonym pass so we don't re-offer them as candidates to Gemini."""
    used: set[tuple[int, str]] = set()
    for f in facts.found():
        if f.source != "tables" or not f.evidence:
            continue
        key = _normalize(f.evidence)
        for idx, table in enumerate(tables_json.get("tables", [])):
            for row in table.get("rows") or []:
                li = row.get("line_item") or row.get("description")
                if isinstance(li, str) and _normalize(li) == key:
                    used.add((idx, key))
                    break
    return used


def run_ai_fallback(
    facts: ResolvedFactSet,
    tables_json: dict,
    taxonomy: Taxonomy,
) -> ResolvedFactSet:
    """Take the partly-resolved fact set and use Gemini to fill what's missing.

    Mutates and returns the same ResolvedFactSet so the caller can chain it
    after `map_concepts`.
    """
    missing = [
        f for f in facts.missing()
        if f.section_id in TABLE_SECTIONS
    ]
    if not missing:
        return facts

    candidates = _collect_candidate_rows(
        tables_json, _existing_evidence_keys(facts, tables_json),
    )
    if not candidates:
        return facts

    prompt = _build_prompt(missing, candidates)
    raw = query_gemini_text(prompt)
    data = _parse_json(raw)

    row_lookup = {c["row_id"]: c for c in candidates}

    by_id = {f.business_term: f for f in facts.facts}
    used_rows: set[str] = set()

    for mapping in data.get("mappings", []) or []:
        cid = mapping.get("concept_id")
        rid = mapping.get("row_id")
        fact = by_id.get(cid)
        if not fact:
            continue
        if not rid or rid not in row_lookup or rid in used_rows:
            # Stay missing, but record the AI reasoning for debugging.
            fact.reason = f"ai: {mapping.get('reason', 'no match')}"
            continue
        row = row_lookup[rid]
        used_rows.add(rid)
        fact.status = "found"
        fact.source = "tables"
        fact.value_cy = row["value_cy"]
        fact.value_py = row["value_py"]
        fact.currency = row["currency"]
        fact.evidence = row["line_item"]
        fact.page = row["page"]
        fact.matched_via = f"ai:{mapping.get('confidence', 'medium')}"

    return facts
