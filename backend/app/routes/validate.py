from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional

from app.services.extractor import extract_with_document_ai
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
    pdf_bytes = await file.read()

    # Step 1: Document AI structured extraction
    doc_data = extract_with_document_ai(pdf_bytes)

    metadata = {
        "report_type": report_type,
        "period": period,
        "currency": currency,
        "reporting_scale": reporting_scale,
    }

    # Step 2: Run rules — Document AI for data checks, Gemini for judgment
    results = run_rules(pdf_bytes, doc_data, sector, metadata)

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skip")

    return {
        "filename": file.filename,
        "sector": sector,
        "extraction": {
            "method": "document_ai + gemini",
            "page_count": doc_data["page_count"],
            "text_length": len(doc_data["full_text"]),
        },
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
        },
        "results": results,
    }
