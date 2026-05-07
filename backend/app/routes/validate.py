import time

from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional

from app.services.extractor import get_pdf_info
from app.services.storage import upload_pdf
from app.rules.engine import run_rules

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

    # Step 3: Run rules — batched Gemini calls for judgment
    t0 = time.time()
    results = run_rules(pdf_bytes, doc_data, sector, metadata)
    t_rules = time.time() - t0

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
            "method": "pymupdf + gemini (batched)",
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
            "rules_seconds": round(t_rules, 1),
        },
        "results": results,
    }
