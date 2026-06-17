"""PDF Tables — generic extraction of every table in a PDF.

Works for any PDF (financial statements, technical reports, etc.). Two-stage:
inventory + per-table extraction in parallel.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.pdf_table_extractor import extract_all_tables

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pdf-tables", tags=["pdf-tables"])


@router.post("/extract")
async def extract_tables(
    file: UploadFile = File(...),
    priority_only: bool = True,
):
    """Extract tables from a PDF as structured JSON.

    priority_only=true (default) — fast mode: only the 4 primary statements
        (Balance Sheet, P&L/OCI, Cash Flow, Changes in Equity) plus the
        revenue note. ~5 tables, finishes in seconds.
    priority_only=false — full sweep over every table the inventory finds.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF is empty")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF (bad signature)")

    t_start = time.time()
    try:
        result = extract_all_tables(pdf_bytes, priority_only=priority_only)
    except Exception as exc:
        logger.exception("PDF table extraction failed")
        raise HTTPException(status_code=502, detail=f"Extraction failed: {exc}")

    total_seconds = round(time.time() - t_start, 1)
    return {
        "filename": file.filename,
        "success": True,
        "mode": result.get("mode", "full"),
        "page_count": result["page_count"],
        "table_count_inventory": result["table_count_inventory"],
        "table_count_selected": result.get("table_count_selected", result["table_count_inventory"]),
        "table_count_extracted": result["table_count_extracted"],
        "table_count_timed_out": result.get("table_count_timed_out", 0),
        "partial": result.get("partial", False),
        "total_rows": result["total_rows"],
        "extraction_seconds": result["elapsed_seconds"],
        "total_seconds": total_seconds,
        "tables": result["tables"],
    }
