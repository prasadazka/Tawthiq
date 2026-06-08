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
- column_count: number of data columns

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
structured JSON. Use the title and page as anchors. If the table spans
multiple pages, collect rows from ALL pages.

ORIENTATION & LAYOUT:
- Tables may be ROTATED 90° (landscape on a portrait page). Read in natural order.
- Multi-line column headers join into one space-separated string.
- Empty cells / dashes → null. "0" stays 0. Numbers in parens are negative: "(1,234)" → -1234.

YEAR / PERIOD HANDLING:
- If columns are year-dated (e.g. "31 December 2025", "31 December 2024"),
  use the date itself as the column key — don't collapse two years into one.

OUTPUT SHAPE (JSON only, no markdown):
{{
  "table_id": "{table_id}",
  "found": true|false,
  "page": <int>,
  "title_as_printed": "<exact heading from PDF>",
  "columns": ["<col1>", "<col2>", ...],
  "rows": [{{"<col1>": <value>, "<col2>": <value>, ...}}, ...],
  "currency": "SAR" | "USD" | "INR" | null,
  "notes": null | "<one short caveat>"
}}

NEVER invent rows. If the table cannot be found, set found=false rows=[].
Return ONLY the JSON object now.
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
    return json.loads(text)


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


def extract_all_tables(pdf_bytes: bytes, max_workers: int = 6) -> dict:
    """Two-pass extraction: inventory + parallel per-table extraction."""
    t_start = time.time()

    # Page count via PyMuPDF (cheap)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    doc.close()

    # 1. Inventory
    logger.info("PDF tables: running inventory pass")
    inv = inventory_tables(pdf_bytes)
    tables = inv.get("tables", [])

    # 2. Parallel extraction
    extracted: list[dict] = []
    if tables:
        logger.info(f"PDF tables: extracting {len(tables)} tables in parallel")
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
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
