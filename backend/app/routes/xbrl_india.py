"""Indian XBRL endpoints — extraction + validation (generation in next phase)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from pydantic import BaseModel

from app.services.extractor import get_pdf_info
from app.xbrl.excel_generator import generate_excel
from app.xbrl.extractor import XBRLDataExtractor
from app.xbrl.template_generator import generate_xbrl as generate_xbrl_from_template
from app.xbrl.validator import IndianXBRLValidator
from app.xbrl.xml_validator import XBRLXMLValidator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/xbrl/india", tags=["xbrl-india"])

# Config paths — relative to backend/ working dir
CONFIG_DIR = Path(__file__).parent.parent / "xbrl" / "india"
EXTRACTION_SCHEMA = CONFIG_DIR / "extraction_schema.yml"
VALIDATION_RULES = CONFIG_DIR / "validation_rules.yml"
CONTEXT_TEMPLATE = CONFIG_DIR / "context_template.yml"
TAXONOMY_MAPPING = CONFIG_DIR / "taxonomy_mapping.yml"


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


@router.post("/generate")
async def generate_xbrl(
    file: UploadFile = File(...),
    skip_validation: bool = Form(False),
):
    """End-to-end: PDF → extract → validate → generate XBRL XML.

    If validation passes (or skip_validation=true), returns the XBRL XML file
    as a download. Otherwise returns the validation report as JSON.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    t_start = time.time()
    pdf_bytes = await file.read()
    doc_info = get_pdf_info(pdf_bytes)

    # 1. Extract
    extractor = XBRLDataExtractor(EXTRACTION_SCHEMA)
    extract_result = extractor.extract(pdf_bytes, doc_info.get("full_text", ""))
    if not extract_result.success:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {extract_result.error}")

    # 2. Validate
    validator = IndianXBRLValidator(VALIDATION_RULES)
    report = validator.validate(extract_result.data)

    if not report.passed and not skip_validation:
        # Block — return failures as JSON
        return {
            "filename": file.filename,
            "success": False,
            "stage": "validation",
            "ready_for_xbrl": False,
            "validation": {
                "passed": False,
                "blocking_failures": [
                    {"rule_id": r.rule_id, "name": r.name, "message": r.message}
                    for r in report.blocking_failures
                ],
                "warnings": [
                    {"rule_id": r.rule_id, "name": r.name, "message": r.message}
                    for r in report.warnings
                ],
            },
            "extraction_data": extract_result.data,
            "hint": "Fix the blocking failures above, or retry with skip_validation=true.",
        }

    # 3. Generate XBRL
    gen_result = generate_xbrl_from_template(extract_result.data)
    if not gen_result.success:
        raise HTTPException(status_code=500, detail=f"XBRL generation failed: {gen_result.error}")

    total_seconds = round(time.time() - t_start, 1)
    logger.info(
        f"XBRL generated for {file.filename}: {gen_result.facts_filled}/{gen_result.fact_count} facts filled, "
        f"{gen_result.context_count} contexts, {total_seconds}s"
    )

    # Return as downloadable XML (UTF-16 encoded, matching Indian convention)
    xml_bytes = gen_result.xml.encode("utf-16")
    headers = {
        "Content-Disposition": f'attachment; filename="{gen_result.filename}"',
        "X-Tawthiq-Facts": f"{gen_result.facts_filled}/{gen_result.fact_count}",
        "X-Tawthiq-Contexts": str(gen_result.context_count),
        "X-Tawthiq-Validation-Passed": str(report.passed).lower(),
        "X-Tawthiq-Warnings": str(len(report.warnings)),
        "X-Tawthiq-Elapsed-Seconds": str(total_seconds),
    }
    return Response(content=xml_bytes, media_type="application/xml", headers=headers)


@router.post("/generate-debug")
async def generate_xbrl_debug(
    file: UploadFile = File(...),
    skip_validation: bool = Form(True),
):
    """Same as /generate but returns JSON (XML as base64) for inspection."""
    import base64

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    t_start = time.time()
    pdf_bytes = await file.read()
    doc_info = get_pdf_info(pdf_bytes)

    extractor = XBRLDataExtractor(EXTRACTION_SCHEMA)
    extract_result = extractor.extract(pdf_bytes, doc_info.get("full_text", ""))
    if not extract_result.success:
        return {"success": False, "error": extract_result.error}

    validator = IndianXBRLValidator(VALIDATION_RULES)
    report = validator.validate(extract_result.data)

    gen_result = generate_xbrl_from_template(extract_result.data)
    if not gen_result.success:
        return {"success": False, "error": gen_result.error}

    return {
        "success": True,
        "filename": gen_result.filename,
        "elapsed_seconds": round(time.time() - t_start, 1),
        "validation": {
            "passed": report.passed,
            "summary": report.summary,
            "blocking_failures": [
                {"rule_id": r.rule_id, "message": r.message}
                for r in report.blocking_failures
            ],
        },
        "xbrl_stats": {
            "fact_count": gen_result.fact_count,
            "facts_filled": gen_result.facts_filled,
            "context_count": gen_result.context_count,
            "xml_size_chars": len(gen_result.xml),
        },
        "xbrl_xml_preview": gen_result.xml[:3000],
        "xbrl_xml_base64": base64.b64encode(gen_result.xml.encode("utf-16")).decode("ascii"),
    }


# ─── XML editor support ───────────────────────────────────────────────────────

class XMLValidationRequest(BaseModel):
    xml: str


@router.post("/validate-xml")
async def validate_xml(req: XMLValidationRequest):
    """Validate an XBRL XML document (after potential user edits).

    Checks: XML well-formedness, required elements, context/unit references,
    and lists facts with empty values that the user may want to fill in.
    """
    validator = XBRLXMLValidator()
    report = validator.validate(req.xml)
    return {
        "valid": report.valid,
        "well_formed": report.well_formed,
        "stats": report.stats,
        "errors": [
            {
                "code": i.code,
                "message": i.message,
                "line": i.line,
                "column": i.column,
                "element": i.element,
            }
            for i in report.errors
        ],
        "warnings": [
            {"code": i.code, "message": i.message, "line": i.line}
            for i in report.warnings
        ],
        "empty_facts": [
            {"tag": e.tag, "context_ref": e.context_ref, "line": e.line, "raw_xml": e.raw_xml}
            for e in report.empty_facts
        ],
    }


class XMLDownloadRequest(BaseModel):
    xml: str
    filename: str = "output.xml"


@router.post("/download-xml")
async def download_xml(req: XMLDownloadRequest):
    """Re-package edited XML as a downloadable UTF-16 file."""
    xml_bytes = req.xml.encode("utf-16")
    headers = {
        "Content-Disposition": f'attachment; filename="{req.filename}"',
    }
    return Response(content=xml_bytes, media_type="application/xml", headers=headers)


@router.post("/generate-excel")
async def generate_excel_endpoint(file: UploadFile = File(...)):
    """End-to-end: PDF → extract → produce multi-sheet Excel workbook.

    Returns an .xlsx file the user can download to inspect every extracted
    field side-by-side with empty cells highlighted (yellow). Useful for
    reviewing AI extraction quality and comparing against the source.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    pdf_bytes = await file.read()
    doc_info = get_pdf_info(pdf_bytes)

    extractor = XBRLDataExtractor(EXTRACTION_SCHEMA)
    er = extractor.extract(pdf_bytes, doc_info.get("full_text", ""))
    if not er.success:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {er.error}")

    excel = generate_excel(er.data)
    if not excel.success:
        raise HTTPException(status_code=500, detail=f"Excel generation failed: {excel.error}")

    headers = {
        "Content-Disposition": f'attachment; filename="{excel.filename}"',
        "X-Tawthiq-Sheets": str(excel.sheet_count),
        "X-Tawthiq-Cells": str(excel.cell_count),
    }
    return Response(
        content=excel.xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


class ExcelFromJSONRequest(BaseModel):
    data: dict


@router.post("/generate-excel-from-json")
async def generate_excel_from_json(req: ExcelFromJSONRequest):
    """Skip extraction — generate Excel directly from an existing JSON payload.

    Useful inside the editor flow where the frontend already has the extracted
    data and wants to download the Excel without re-running Gemini.
    """
    excel = generate_excel(req.data)
    if not excel.success:
        raise HTTPException(status_code=500, detail=f"Excel generation failed: {excel.error}")
    headers = {
        "Content-Disposition": f'attachment; filename="{excel.filename}"',
        "X-Tawthiq-Sheets": str(excel.sheet_count),
    }
    return Response(
        content=excel.xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
