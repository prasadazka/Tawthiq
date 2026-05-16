"""Indian XBRL endpoints — extraction + validation (generation in next phase)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.extractor import get_pdf_info
from app.xbrl.extractor import XBRLDataExtractor
from app.xbrl.validator import IndianXBRLValidator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/xbrl/india", tags=["xbrl-india"])

# Config paths — relative to backend/ working dir
CONFIG_DIR = Path(__file__).parent.parent / "xbrl" / "india"
EXTRACTION_SCHEMA = CONFIG_DIR / "extraction_schema.yml"
VALIDATION_RULES = CONFIG_DIR / "validation_rules.yml"


@router.post("/extract")
async def extract_and_validate(file: UploadFile = File(...)):
    """Extract structured data from an Indian audit PDF and run pre-XBRL validation.

    Returns the extracted JSON plus a validation report (all 33 rule results).
    XBRL generation is a separate endpoint (added in Phase 5).
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    t_start = time.time()
    pdf_bytes = await file.read()
    doc_info = get_pdf_info(pdf_bytes)

    # Step 1: Extract structured data via Gemini
    t0 = time.time()
    extractor = XBRLDataExtractor(EXTRACTION_SCHEMA)
    result = extractor.extract(pdf_bytes, doc_info.get("full_text", ""))
    extract_seconds = round(time.time() - t0, 1)

    if not result.success:
        return {
            "filename": file.filename,
            "success": False,
            "stage": "extraction",
            "error": result.error,
            "raw_response_preview": result.raw_response[:500] if result.raw_response else "",
            "extract_seconds": extract_seconds,
        }

    # Step 2: Validate the extracted JSON against MCA-filing rules
    t0 = time.time()
    validator = IndianXBRLValidator(VALIDATION_RULES)
    report = validator.validate(result.data)
    validate_seconds = round(time.time() - t0, 2)

    total_seconds = round(time.time() - t_start, 1)

    return {
        "filename": file.filename,
        "success": True,
        "ready_for_xbrl": report.passed,
        "timings": {
            "extract_seconds": extract_seconds,
            "validate_seconds": validate_seconds,
            "total_seconds": total_seconds,
        },
        "extraction": {
            "page_count": doc_info.get("page_count"),
            "data": result.data,
        },
        "validation": {
            "passed": report.passed,
            "summary": report.summary,
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "category": r.category,
                    "severity": r.severity,
                    "status": r.status,
                    "message": r.message,
                    "actual": r.actual,
                }
                for r in report.rules
            ],
            "blocking_failures": [
                {"rule_id": r.rule_id, "name": r.name, "message": r.message}
                for r in report.blocking_failures
            ],
            "warnings": [
                {"rule_id": r.rule_id, "name": r.name, "message": r.message}
                for r in report.warnings
            ],
        },
    }
