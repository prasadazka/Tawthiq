"""Indian XBRL endpoints — extraction + validation (generation in next phase)."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from pydantic import BaseModel

from app.services.excel_extractor import excel_to_markdown, is_valid_excel
from app.services.extractor import get_pdf_info
from app.services.merger import merge_extractions
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


async def _read_upload(file: UploadFile, suffix: str, label: str) -> bytes:
    if not file.filename or not file.filename.lower().endswith(suffix):
        raise HTTPException(status_code=400, detail=f"{label} must end with {suffix}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail=f"{label} is empty")
    return data


async def _extract_combined(pdf_bytes: bytes, xlsx_bytes: bytes) -> dict:
    """Run PDF + Excel extraction in parallel and merge.

    Returns:
        {
          "data": merged extraction dict,
          "pdf_data": raw PDF extraction,
          "xlsx_data": raw Excel extraction,
          "provenance": {path: "pdf"|"xlsx"},
          "conflicts": [...],
          "page_count": int,
          "timings": {...},
          "errors": {pdf?: str, xlsx?: str},
        }
    """
    if not is_valid_excel(xlsx_bytes):
        raise HTTPException(status_code=400, detail="Invalid Excel file (bad signature)")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF file (bad signature)")

    t0 = time.time()
    doc_info = get_pdf_info(pdf_bytes)
    sheets_md = excel_to_markdown(xlsx_bytes)
    t_prep = round(time.time() - t0, 2)

    extractor = XBRLDataExtractor(EXTRACTION_SCHEMA)

    loop = asyncio.get_running_loop()
    t1 = time.time()
    pdf_task = loop.run_in_executor(
        None, extractor.extract, pdf_bytes, doc_info.get("full_text", "")
    )
    xlsx_task = loop.run_in_executor(None, extractor.extract_from_excel, sheets_md)
    pdf_res, xlsx_res = await asyncio.gather(pdf_task, xlsx_task)
    t_extract = round(time.time() - t1, 1)

    errors: dict[str, str] = {}
    if not pdf_res.success:
        errors["pdf"] = pdf_res.error
    if not xlsx_res.success:
        errors["xlsx"] = xlsx_res.error

    # Hard fail only if both failed.
    if not pdf_res.success and not xlsx_res.success:
        raise HTTPException(
            status_code=502,
            detail=f"Both extractions failed. PDF: {pdf_res.error} | Excel: {xlsx_res.error}",
        )

    pdf_data = pdf_res.data if pdf_res.success else {}
    xlsx_data = xlsx_res.data if xlsx_res.success else {}
    merged, provenance, conflicts = merge_extractions(pdf_data, xlsx_data)

    if conflicts:
        logger.info(f"merge conflicts: {len(conflicts)} numeric values differ significantly between PDF and Excel")

    return {
        "data": merged,
        "pdf_data": pdf_data,
        "xlsx_data": xlsx_data,
        "provenance": provenance,
        "conflicts": conflicts,
        "page_count": doc_info.get("page_count"),
        "sheet_names": list(sheets_md.keys()),
        "timings": {
            "prep_seconds": t_prep,
            "extract_seconds": t_extract,
        },
        "errors": errors,
    }


@router.post("/extract")
async def extract_and_validate(
    file: UploadFile = File(...),
    excel: UploadFile = File(...),
):
    """Extract structured data from PDF + Excel (in parallel) and run pre-XBRL validation.

    Returns the merged extracted JSON plus a validation report (all 33 rule results).
    """
    t_start = time.time()
    pdf_bytes = await _read_upload(file, ".pdf", "PDF")
    xlsx_bytes = await _read_upload(excel, ".xlsx", "Excel")

    combined = await _extract_combined(pdf_bytes, xlsx_bytes)

    t0 = time.time()
    validator = IndianXBRLValidator(VALIDATION_RULES)
    report = validator.validate(combined["data"])
    validate_seconds = round(time.time() - t0, 2)

    total_seconds = round(time.time() - t_start, 1)

    return {
        "filename": file.filename,
        "excel_filename": excel.filename,
        "success": True,
        "ready_for_xbrl": report.passed,
        "timings": {
            "extract_seconds": combined["timings"]["extract_seconds"],
            "validate_seconds": validate_seconds,
            "total_seconds": total_seconds,
        },
        "extraction": {
            "page_count": combined["page_count"],
            "sheet_names": combined["sheet_names"],
            "data": combined["data"],
            "provenance": combined["provenance"],
            "conflicts": combined["conflicts"],
            "extraction_errors": combined["errors"],
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
    excel: UploadFile = File(...),
    skip_validation: bool = Form(False),
):
    """End-to-end: PDF + Excel → extract → validate → generate XBRL XML.

    If validation passes (or skip_validation=true), returns the XBRL XML file
    as a download. Otherwise returns the validation report as JSON.
    """
    t_start = time.time()
    pdf_bytes = await _read_upload(file, ".pdf", "PDF")
    xlsx_bytes = await _read_upload(excel, ".xlsx", "Excel")

    combined = await _extract_combined(pdf_bytes, xlsx_bytes)
    merged_data = combined["data"]

    validator = IndianXBRLValidator(VALIDATION_RULES)
    report = validator.validate(merged_data)

    if not report.passed and not skip_validation:
        return {
            "filename": file.filename,
            "excel_filename": excel.filename,
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
            "extraction_data": merged_data,
            "hint": "Fix the blocking failures above, or retry with skip_validation=true.",
        }

    gen_result = generate_xbrl_from_template(merged_data)
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
    excel: UploadFile = File(...),
    skip_validation: bool = Form(True),
):
    """Same as /generate but returns JSON (XML as base64) for inspection."""
    import base64

    t_start = time.time()
    pdf_bytes = await _read_upload(file, ".pdf", "PDF")
    xlsx_bytes = await _read_upload(excel, ".xlsx", "Excel")

    combined = await _extract_combined(pdf_bytes, xlsx_bytes)
    merged_data = combined["data"]

    validator = IndianXBRLValidator(VALIDATION_RULES)
    report = validator.validate(merged_data)

    gen_result = generate_xbrl_from_template(merged_data)
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
async def generate_excel_endpoint(
    file: UploadFile = File(...),
    excel: UploadFile = File(...),
):
    """End-to-end: PDF + Excel → extract → produce multi-sheet review workbook.

    Returns an .xlsx file the user can download to inspect every extracted
    field side-by-side with empty cells highlighted (yellow).
    """
    pdf_bytes = await _read_upload(file, ".pdf", "PDF")
    xlsx_bytes = await _read_upload(excel, ".xlsx", "Excel")

    combined = await _extract_combined(pdf_bytes, xlsx_bytes)
    excel_out = generate_excel(combined["data"])
    if not excel_out.success:
        raise HTTPException(status_code=500, detail=f"Excel generation failed: {excel_out.error}")

    headers = {
        "Content-Disposition": f'attachment; filename="{excel_out.filename}"',
        "X-Tawthiq-Sheets": str(excel_out.sheet_count),
        "X-Tawthiq-Cells": str(excel_out.cell_count),
    }
    return Response(
        content=excel_out.xlsx_bytes,
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
