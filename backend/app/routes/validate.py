import asyncio
import logging
import time

from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional

from app.services.extractor import get_pdf_info
from app.services.pdf_table_extractor import extract_all_tables
from app.services.storage import upload_pdf
from app.rules.engine import run_rules

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["validate"])


@router.post("/validate")
async def validate_document(
    file: UploadFile = File(..., description="PDF file to validate"),
    sector: str = Form("all", description="Sector: all, banking_insurance, npo"),
    report_type: Optional[str] = Form(None, description="consolidated or standalone"),
    period: Optional[str] = Form(None, description="annual or quarterly"),
    currency: Optional[str] = Form(None, description="Expected currency"),
    reporting_scale: Optional[str] = Form(None, description="thousands, millions, or actuals"),
):
    t_total = time.time()
    pdf_bytes = await file.read()

    # Step 1: Store PDF in GCS
    t0 = time.time()
    gcs_path = upload_pdf(pdf_bytes, file.filename or "document.pdf")
    t_upload = time.time() - t0

    # Step 2: PyMuPDF extraction — page count + full text
    t0 = time.time()
    doc_data = get_pdf_info(pdf_bytes)
    t_extraction = time.time() - t0

    metadata = {
        "report_type": report_type,
        "period": period,
        "currency": currency,
        "reporting_scale": reporting_scale,
    }

    # Step 3 + 4: Run rules and table extraction concurrently — both are
    # parallel Gemini-call orchestrators internally, so we offload each to a
    # background thread and await both. Wall clock = max of the two.
    t0 = time.time()
    loop = asyncio.get_running_loop()
    rules_task = loop.run_in_executor(
        None, run_rules, pdf_bytes, doc_data, sector, metadata
    )
    tables_task = loop.run_in_executor(None, extract_all_tables, pdf_bytes)

    results, tables_payload = await asyncio.gather(
        rules_task, tables_task, return_exceptions=True
    )
    t_parallel = time.time() - t0

    # Handle rules failure as fatal (existing contract); table failure is soft.
    if isinstance(results, BaseException):
        logger.exception("Rules engine failed", exc_info=results)
        raise results

    if isinstance(tables_payload, BaseException):
        logger.warning(f"Table extraction failed (continuing without tables): {tables_payload}")
        tables_payload = {
            "page_count": doc_data.get("page_count"),
            "table_count_inventory": 0,
            "table_count_extracted": 0,
            "total_rows": 0,
            "elapsed_seconds": 0,
            "tables": [],
            "error": str(tables_payload),
        }

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skip")
    not_applicable = sum(1 for r in results if r["status"] == "not_applicable")

    t_total_elapsed = time.time() - t_total

    return {
        "filename": file.filename,
        "gcs_path": gcs_path,
        "sector": sector,
        "extraction": {
            "method": "pymupdf + gemini (batched) + table extraction",
            "page_count": doc_data["page_count"],
            "text_length": len(doc_data["full_text"]),
        },
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "not_applicable": not_applicable,
        },
        "timing": {
            "total_seconds": round(t_total_elapsed, 1),
            "upload_seconds": round(t_upload, 1),
            "extraction_seconds": round(t_extraction, 1),
            "parallel_seconds": round(t_parallel, 1),
        },
        "results": results,
        "tables": {
            "table_count_inventory": tables_payload.get("table_count_inventory", 0),
            "table_count_extracted": tables_payload.get("table_count_extracted", 0),
            "total_rows": tables_payload.get("total_rows", 0),
            "items": tables_payload.get("tables", []),
        },
    }
