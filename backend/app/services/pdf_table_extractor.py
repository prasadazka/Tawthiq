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
from concurrent.futures import TimeoutError as FuturesTimeoutError

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

──────────────────────────────────────────────────────────────────────────
SCRIPT DIRECTION — RTL vs LTR (Arabic / Hebrew vs Latin):

Determine the table's primary script direction and set "direction" in the
output to "rtl" or "ltr".

- LTR (English, French, Latin scripts): physically left-to-right.
    Page layout: [description | Notes | newer year | older year]
    Set "direction": "ltr".
- RTL (Arabic, Hebrew, Farsi): physically right-to-left.
    Page layout (visually): [older year | newer year | Notes | description]
    where description sits on the RIGHT side of the page.
    Set "direction": "rtl".

REGARDLESS of script direction, the "columns" array MUST be emitted in
READING ORDER — i.e. the description/line_item column is ALWAYS the FIRST
element of the columns array, followed by Notes (if any), then value
columns from latest year to earliest year.

This means:
- LTR table on the page: columns array order matches physical left-to-right.
- RTL table on the page: columns array order matches reading order
  (description first), which is the visual RIGHT-to-LEFT scan. Do NOT
  output the physically-leftmost (= oldest year) column first.

The frontend uses "direction" to render the table in the right CSS
direction. The data itself stays consistent (description-first) so
downstream code does not have to special-case the script.

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

──────────────────────────────────────────────────────────────────────────
MOVEMENT / ROLL-FORWARD TABLES — CONSOLIDATE PARALLEL SUB-SECTIONS:

Many Saudi/Indian financial reports show a movement schedule (e.g.
"Changes in defined benefit obligation", "PPE movement", "Lease liability
movement") as TWO STACKED SUB-SECTIONS — one block of rows for the prior
year followed by another block of rows for the current year, each block
repeating the same line-item names (Opening balance, Interest cost,
Current service cost, etc.).

⚠ DO NOT emit those as 14 rows where each row has a value in only ONE
   year column and a dash/null in the other. That is wrong.

✅ CONSOLIDATE into ONE table where each unique line-item appears ONCE
   with BOTH year columns populated side-by-side. The result is a normal
   movement table.

Matching rules when consolidating:
- Treat year-specific phrasing as equivalent: "at 1 January 2024" and
  "at 1 January 2025" both map to "at beginning of year".
- "at 31 December 2024" and "at 31 December 2025" both map to "at end
  of year".
- Sign variants are still the same line: "Re-measurements gains in OCI"
  and "Re-measurement loss in OCI" → one row "Re-measurements
  (gain)/loss in OCI".
- Items that only exist in one of the years (e.g. "Additions from
  acquisition") keep the value for the year they appear and null for the
  other year — but only ONE row, not two.

Result for the example above: ~8 consolidated rows, not 14.

OUTPUT SHAPE (JSON only — no markdown, no preamble):
{{
  "table_id": "{table_id}",
  "found": true|false,
  "page": <int>,
  "title_as_printed": "<exact heading from PDF, in the PDF's native script>",
  "direction": "rtl" | "ltr",
  "columns": [<column keys in READING order — description/line_item FIRST, then Notes, then value columns latest-year-first; use "line_item" only when the PDF header is blank>],
  "rows": [<one object per data row, with one key per column from the list above>],
  "currency": "SAR" | "USD" | "INR" | "EUR" | null,
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
    """Single Gemini call — returns the list of tables in the PDF.

    Kept for callers that want the simple one-shot behavior; the production
    pipeline uses `inventory_tables_parallel` instead.
    """
    raw = query_with_gemini(pdf_bytes, INVENTORY_PROMPT)
    return _parse_json(raw)


def _split_pdf_into_chunks(pdf_bytes: bytes, pages_per_chunk: int = 20) -> list[tuple[int, bytes]]:
    """Split a PDF into fixed-size page chunks. Returns [(start_page, chunk_pdf_bytes), …]
    where start_page is the 1-indexed page number the chunk's first page maps
    to in the original document. Used to parallelize the inventory pass."""
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(src)
    chunks: list[tuple[int, bytes]] = []
    for start_zero in range(0, total, pages_per_chunk):
        end_zero = min(start_zero + pages_per_chunk - 1, total - 1)
        chunk_doc = fitz.open()
        chunk_doc.insert_pdf(src, from_page=start_zero, to_page=end_zero)
        chunks.append((start_zero + 1, chunk_doc.tobytes()))
        chunk_doc.close()
    src.close()
    return chunks


def inventory_tables_parallel(
    pdf_bytes: bytes,
    pages_per_chunk: int = 20,
    max_workers: int = 6,
) -> dict:
    """Run the inventory pass in parallel over page chunks, then merge.

    For a 100-page PDF this turns one ~4-min sequential Gemini call into
    ~5 parallel ~50s calls. Per-chunk responses are merged and the page
    numbers re-mapped to the original document. Skipping chunk overlap
    means tables that straddle a chunk boundary (rare) may be inventoried
    twice or split — both still get extracted in the per-table phase."""
    chunks = _split_pdf_into_chunks(pdf_bytes, pages_per_chunk=pages_per_chunk)
    if len(chunks) <= 1:
        return inventory_tables(pdf_bytes)

    def _one(chunk_args: tuple[int, bytes]) -> tuple[int, dict]:
        start_page, chunk_bytes = chunk_args
        raw = query_with_gemini(chunk_bytes, INVENTORY_PROMPT)
        return start_page, _parse_json(raw)

    merged_tables: list[dict] = []
    workers = min(max_workers, len(chunks))
    logger.info(
        f"PDF tables inventory: {len(chunks)} chunks × {pages_per_chunk} pages, "
        f"{workers} parallel workers"
    )
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_one, c): c[0] for c in chunks}
        for fut in as_completed(futures):
            start_page = futures[fut]
            try:
                _, payload = fut.result()
            except Exception as exc:
                logger.warning(f"inventory chunk starting p.{start_page} failed: {exc}")
                continue
            # Re-map per-chunk page numbers (1-indexed within the chunk) to
            # absolute page numbers in the original PDF.
            for t in payload.get("tables", []):
                local_page = t.get("page")
                if isinstance(local_page, int) and local_page > 0:
                    t["page"] = start_page + local_page - 1
                merged_tables.append(t)

    # Stable sort by page number for downstream code.
    merged_tables.sort(key=lambda t: t.get("page") if isinstance(t.get("page"), int) else 9999)
    return {"total_tables": len(merged_tables), "tables": merged_tables}


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


# The 4 universal IFRS primary statements. Hardcoded so priority_only mode can
# skip the inventory pass entirely and ask Gemini for each by name in parallel.
PRIMARY_TARGETS: list[dict] = [
    {
        "table_id": "balance_sheet",
        "title": (
            "Consolidated Statement of Financial Position (Balance Sheet) / "
            "قائمة المركز المالي الموحدة — primary statement showing assets, liabilities, "
            "and equity at year-end with comparative prior year"
        ),
        "page": "find it",
        "category": "primary_statement",
    },
    {
        "table_id": "profit_or_loss_and_oci",
        "title": (
            "Consolidated Statement of Profit or Loss and Other Comprehensive Income / "
            "قائمة الربح أو الخسارة والدخل الشامل الآخر الموحدة — primary statement showing "
            "revenue, expenses, and profit for the year with comparative prior year"
        ),
        "page": "find it",
        "category": "primary_statement",
    },
    {
        "table_id": "cash_flows",
        "title": (
            "Consolidated Statement of Cash Flows / قائمة التدفقات النقدية الموحدة — primary "
            "statement showing operating, investing, and financing cash flows with comparative prior year"
        ),
        "page": "find it",
        "category": "primary_statement",
    },
    {
        "table_id": "changes_in_equity",
        "title": (
            "Consolidated Statement of Changes in Equity / قائمة التغيرات في حقوق الملكية الموحدة "
            "— primary statement showing movements in share capital, reserves, and retained earnings "
            "across both current and prior year"
        ),
        "page": "find it",
        "category": "primary_statement",
    },
]


def extract_all_tables(
    pdf_bytes: bytes,
    max_workers: int = 48,
    extract_budget_seconds: int = 1200,
    inventory_pages_per_chunk: int = 20,
    inventory_workers: int = 6,
    priority_only: bool = True,
) -> dict:
    """Two-pass extraction: parallel inventory + parallel per-table extraction.

    extract_budget_seconds caps the per-table extraction phase. When the
    budget is exceeded, every future that hasn't completed is marked as
    timed-out and the request returns with `partial: true`. The inventory
    pass is not budgeted but runs across page chunks in parallel, so for
    a 100-page PDF it finishes in ~1 minute instead of ~4 minutes.

    max_workers default 48 — Vertex AI Gemini Flash easily handles this many
    concurrent requests per project. A typical 80-table Saudi PDF then
    finishes one extract round in ~25 s instead of three rounds at 24 workers.
    """
    t_start = time.time()

    # Page count via PyMuPDF (cheap)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    doc.close()

    # 1. Inventory pass — only when running a full sweep. In priority mode we
    # skip the inventory entirely (saves ~50s) and ask Gemini for the 4 known
    # primary statements directly by name in parallel.
    if priority_only:
        tables = [dict(t) for t in PRIMARY_TARGETS]
        inventory_total = 0
        logger.info(
            f"PDF tables: priority_only=True — skipping inventory, extracting "
            f"{len(tables)} primary statements directly"
        )
    else:
        logger.info("PDF tables: running parallel inventory pass")
        t_inv = time.time()
        inv = inventory_tables_parallel(
            pdf_bytes,
            pages_per_chunk=inventory_pages_per_chunk,
            max_workers=inventory_workers,
        )
        tables = inv.get("tables", [])
        inventory_total = len(tables)
        logger.info(
            f"PDF tables: inventory complete in {round(time.time()-t_inv, 1)}s "
            f"({inventory_total} tables across {page_count} pages)"
        )

    # 2. Parallel extraction with a total wall-clock budget so a single hung
    #    future cannot block the whole request. When the budget is hit, every
    #    unfinished future is recorded as timed_out and we return partial.
    extracted: list[dict] = []
    partial = False
    timed_out_count = 0
    if tables:
        workers = min(max_workers, max(1, len(tables)))
        logger.info(
            f"PDF tables: extracting {len(tables)} tables in parallel "
            f"({workers} workers, budget {extract_budget_seconds}s)"
        )
        ex = ThreadPoolExecutor(max_workers=workers)
        try:
            futures = {ex.submit(extract_table, pdf_bytes, t): t for t in tables}
            try:
                for fut in as_completed(futures, timeout=extract_budget_seconds):
                    extracted.append(fut.result())
            except FuturesTimeoutError:
                partial = True
                logger.warning(
                    f"PDF tables: extract budget ({extract_budget_seconds}s) exceeded — "
                    f"returning partial results"
                )
                # Collect whatever has already completed; mark the rest as timed-out.
                for fut, src_table in futures.items():
                    if fut.done():
                        try:
                            extracted.append(fut.result())
                        except Exception as exc:
                            extracted.append({
                                "table_id": src_table.get("table_id"),
                                "found": False,
                                "error": f"call failed: {exc}",
                                "target_title": src_table.get("title"),
                                "category": src_table.get("category"),
                            })
                    else:
                        timed_out_count += 1
                        extracted.append({
                            "table_id": src_table.get("table_id"),
                            "found": False,
                            "error": (
                                f"timed out — extraction budget of "
                                f"{extract_budget_seconds}s exceeded before this table finished"
                            ),
                            "target_title": src_table.get("title"),
                            "category": src_table.get("category"),
                            "page": src_table.get("page"),
                        })
        finally:
            # Don't wait for hung futures to drain — let them die with the worker pool.
            ex.shutdown(wait=False, cancel_futures=True)

    # Sort by page for stable order
    extracted.sort(key=lambda r: (r.get("page") if isinstance(r.get("page"), int) else 9999))

    total_rows = sum(len(r.get("rows", []) or []) for r in extracted)
    elapsed = round(time.time() - t_start, 1)
    return {
        "page_count": page_count,
        "mode": "priority" if priority_only else "full",
        "table_count_inventory": inventory_total,
        "table_count_selected": len(tables),
        "table_count_extracted": sum(1 for r in extracted if r.get("found")),
        "table_count_timed_out": timed_out_count,
        "partial": partial,
        "total_rows": total_rows,
        "elapsed_seconds": elapsed,
        "inventory": tables,
        "tables": extracted,
    }
