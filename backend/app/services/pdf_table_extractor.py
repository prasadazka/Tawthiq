"""PDF table extraction service.

Two-stage extraction:
1. Inventory pass — ask Gemini to enumerate every table in the PDF.
2. Per-table extraction — for each real data table, extract structured rows
   in parallel.

Designed to be PDF-agnostic — no hardcoded company / sheet names.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # PyMuPDF

from app.services.extractor import query_gemini_text, query_with_gemini

logger = logging.getLogger(__name__)


INVENTORY_PROMPT = """You are inventorying every table and schedule in this PDF.

TASK: Return a complete list of EVERY distinct table or numerical schedule
visible in the PDF. A "table" is any structured grid with at least one data
row and one numeric/value column. Include:
- Primary financial statements (balance sheet, P&L, cash flow, equity, OCI)
- Note schedules (PPE movement, intangibles, leases, borrowings, segments,
  related parties, employee benefits, share capital, reserves, fair-value
  hierarchy, maturity analysis, etc.)
- Movement / roll-forward tables
- Reconciliations
- Ratio / KPI tables

EXCLUDE narrative paragraphs that merely look like tables (branch lists,
accounting-policy bullets, useful-life lists with no values, single-cell headings).

For EACH table return:
- table_id: short slug (e.g. "balance_sheet", "ppe_movement")
- title: heading as printed in the PDF
- category: one of [primary_statement, note_schedule, movement_table,
  reconciliation, segment, related_party, fair_value, maturity, kpi, other]
- page: 1-indexed page number where the table starts
- row_count_approx: approximate data row count
- column_count: TOTAL number of columns INCLUDING the leftmost line-item /
  description column (which is almost always present even when its header
  is blank).

Output ONLY valid JSON:
{"total_tables": <int>, "tables": [...]}

No markdown, no preamble.
"""


def _extract_prompt(table: dict) -> str:
    title = table.get("title", "")
    page = table.get("page", "?")
    category = table.get("category", "other")
    table_id = table.get("table_id", "table")

    return f"""You are extracting a specific table from a PDF.

TARGET TABLE:
- id      : {table_id}
- title   : {title}
- page    : {page}
- category: {category}

TASK: Find this exact table in the PDF and return its FULL content as
structured JSON, with HIGH FIDELITY to the PDF's actual column structure.

──────────────────────────────────────────────────────────────────────────
COLUMN-FIDELITY RULES (READ CAREFULLY — most common failure mode):

1. COUNT every column the PDF actually has, left-to-right, BEFORE deciding
   on column keys. Typical financial-statement layout (left → right):
       [description] [Notes] [latest year] [prior year]
   That is FOUR columns. Sometimes only three (no notes), sometimes five
   or more (multi-period comparatives, sub-period columns, etc.).

2. PRESERVE the column order exactly as printed. Do NOT reorder.

3. For each column, the "columns" array key MUST describe what the PDF's
   physical column header literally says:
   - If the header reads "31 December 2025", use "31 December 2025" — NOT
     "current_year", NOT "2025", NOT anything else.
   - If the header reads "Notes", use "Notes".
   - If the header is BLANK (typical for the leftmost description column),
     use "line_item" or "description".
   - NEVER swap a year header with another year's data.

4. The leftmost column is almost always a DESCRIPTION column with text
   labels like "Cash and bank balances", "Trade receivables", "Property,
   plant and equipment", etc. Capture it as a column with header
   "line_item" (or whatever the PDF prints). Each row's value for this
   column is the TEXT label — never a number.

5. CRITICAL — DO NOT SHIFT VALUES BETWEEN COLUMNS. If row says:
       Cash and bank balances    9    2,524,035    916,090
   then the JSON row MUST be:
       {{"line_item": "Cash and bank balances", "Notes": "9",
        "<exact 2025 header>": 2524035, "<exact 2024 header>": 916090}}
   NOT shifted by one column. NOT collapsed into fewer columns.

6. If two year columns are present, you MUST return BOTH with numeric
   values in the correct year's column. Numbers in parens "(1,234)" → -1234.

7. Section-header rows (like "Assets", "Current assets", "Liabilities")
   have ONLY the description field filled; all other columns are null.

──────────────────────────────────────────────────────────────────────────
ORIENTATION & LAYOUT:
- Tables may be ROTATED 90°. Read in natural order after mental rotation.
- Multi-line column headers join into one space-separated string.
- Empty cells / dashes → null. "0" stays 0.

NUMERIC VALUES — MUST BE JSON NUMBERS, NOT STRINGS:
- Every numeric cell must be emitted as a JSON number: 2524035458, not "2524035458".
- Strip thousands separators: "1,234,567" → 1234567 (number, no commas, no quotes).
- Parentheses → negative number: "(1,234)" → -1234 (number, no quotes).
- Decimals preserved: "3.5" → 3.5 (number).
- Only the description column (and Notes column, when it contains references
  like "8-1") should be strings. All value columns are numbers or null.

CORRECT vs WRONG (numeric formatting only — column names are illustrative):
  ✅ CORRECT:   {{"line_item": "Revenues", "Notes": "36", "year_col_A": 2672986045, "year_col_B": 3263352508}}
  ❌ WRONG:     {{"line_item": "Revenues", "Notes": "36", "year_col_A": "2,672,986,045", "year_col_B": "3,263,352,508"}}
  ❌ WRONG:     {{"line_item": "Revenues", "Notes": "36", "year_col_A": "2672986045", "year_col_B": "3263352508"}}

JSON FORMATTING:
- All keys and string values use DOUBLE quotes (").
- No trailing commas.
- No comments.

OUTPUT SHAPE (JSON only — no markdown, no preamble):
{{
  "table_id": "{table_id}",
  "found": true|false,
  "page": <int>,
  "title_as_printed": "<exact heading from PDF>",
  "columns": [<list of column keys in left-to-right order, EXACTLY as the PDF prints headers; use "line_item" only when the PDF header is blank>],
  "rows": [<one object per data row, with one key per column from the list above>],
  "currency": "SAR" | "USD" | "INR" | null,
  "notes": null | "<one short caveat>"
}}

NEVER invent rows. If the table cannot be found, set found=false rows=[].
Return ONLY the JSON object now.
"""


def _parse_json(raw: str) -> dict:
    import re
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
        # Tolerate common LLM JSON mistakes: trailing commas before } or ].
        cleaned = re.sub(r",(\s*[}\]])", r"\1", text)
        return json.loads(cleaned)


def inventory_tables(pdf_bytes: bytes) -> dict:
    """Single Gemini call — returns the list of tables in the PDF."""
    raw = query_with_gemini(pdf_bytes, INVENTORY_PROMPT)
    return _parse_json(raw)


def extract_table(pdf_bytes: bytes, table: dict) -> dict:
    """Extract one table by calling Gemini with a focused prompt."""
    prompt = _extract_prompt(table)
    t0 = time.time()
    try:
        raw = query_with_gemini(pdf_bytes, prompt)
        data = _parse_json(raw)
        data["elapsed_seconds"] = round(time.time() - t0, 1)
        data["target_title"] = table.get("title")
        data["category"] = table.get("category")
        return data
    except Exception as exc:
        return {
            "table_id": table.get("table_id"),
            "found": False,
            "error": str(exc),
            "elapsed_seconds": round(time.time() - t0, 1),
            "target_title": table.get("title"),
            "category": table.get("category"),
        }


def extract_all_tables(pdf_bytes: bytes, max_workers: int = 24) -> dict:
    """Two-pass extraction: inventory + parallel per-table extraction.

    max_workers default 24 = roughly one round of parallel calls for a typical
    Saudi audit PDF (20-40 tables). Vertex AI Gemini Flash supports hundreds
    of concurrent requests per project; 24 keeps us well under any quota
    while still finishing most PDFs in ~60-90s instead of 4+ minutes.
    """
    t_start = time.time()

    # Page count via PyMuPDF (cheap)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    doc.close()

    # 1. Inventory
    logger.info("PDF tables: running inventory pass")
    inv = inventory_tables(pdf_bytes)
    tables = inv.get("tables", [])

    # 2. Parallel extraction — cap workers at the number of tables (no point
    # over-spawning for small PDFs).
    extracted: list[dict] = []
    if tables:
        workers = min(max_workers, max(1, len(tables)))
        logger.info(f"PDF tables: extracting {len(tables)} tables in parallel ({workers} workers)")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(extract_table, pdf_bytes, t): t for t in tables}
            for fut in as_completed(futures):
                extracted.append(fut.result())

    # Sort by page for stable order
    extracted.sort(key=lambda r: (r.get("page") if isinstance(r.get("page"), int) else 9999))

    total_rows = sum(len(r.get("rows", []) or []) for r in extracted)
    elapsed = round(time.time() - t_start, 1)
    return {
        "page_count": page_count,
        "table_count_inventory": len(tables),
        "table_count_extracted": sum(1 for r in extracted if r.get("found")),
        "total_rows": total_rows,
        "elapsed_seconds": elapsed,
        "inventory": tables,
        "tables": extracted,
    }
