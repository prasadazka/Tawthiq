"""Generate the Indian XBRL Excel using a template + cell mapping.

Template: backend/app/xbrl/india/template.xlsx
  - Identical sheet structure, labels, formatting to the original Ramson
    accountant's working-paper file
  - All numeric data cells cleared

Mapping: backend/app/xbrl/india/excel_cell_mapping.yml
  - Tells the generator which JSON path to write into each cell
  - For arrays (shareholders/directors): a 'rows' descriptor expands

For any uploaded PDF:
  - Load the template
  - Apply title overrides (replace "RAMSON…" with the actual company name)
  - Walk the mapping, write each value (blank cells stay blank)
  - Save and return bytes

Result: every Excel produced has EXACTLY the same 12 sheets, same labels,
same column headers, same formatting as the reference Ramson file —
only the numbers change per uploaded PDF.
"""
from __future__ import annotations

import datetime as dt
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from openpyxl import load_workbook
from openpyxl.workbook import Workbook

logger = logging.getLogger(__name__)

# Paths relative to this file
THIS_DIR = Path(__file__).parent
TEMPLATE_PATH = THIS_DIR / "india" / "template.xlsx"
MAPPING_PATH = THIS_DIR / "india" / "excel_cell_mapping.yml"


@dataclass
class ExcelResult:
    success: bool
    xlsx_bytes: bytes = b""
    filename: str = "output.xlsx"
    sheet_count: int = 0
    cells_written: int = 0
    error: str = ""


# ── helpers ──────────────────────────────────────────────────────────────────

def _get(data: dict, path: str, default: Any = None) -> Any:
    """Traverse a dotted JSON path. Returns default if any segment missing."""
    if not path:
        return default
    cur: Any = data
    for seg in path.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return default
        cur = cur[seg]
    return cur if cur is not None else default


def _fmt_date_indian(iso_date: str | None) -> str:
    """Convert YYYY-MM-DD → 31-03-2023 (Indian display)."""
    if not iso_date:
        return ""
    try:
        d = dt.date.fromisoformat(iso_date)
        return d.strftime("%d-%m-%Y")
    except Exception:
        return iso_date


# ── core generator ───────────────────────────────────────────────────────────

def _apply_title_overrides(wb: Workbook, data: dict, overrides: dict) -> int:
    """Replace cleared title cells with extracted company name / dates / CIN."""
    written = 0
    company_name = (_get(data, "company.name") or "COMPANY").upper()
    company_cin = _get(data, "company.cin") or ""
    end_date = _get(data, "reporting_period.end_date")
    end_ind = _fmt_date_indian(end_date)

    fmt_args = dict(
        company_name=company_name,
        company_cin=company_cin,
        end_date=end_date or "",
        end_date_indian=end_ind,
    )

    for sheet_name, cell_map in overrides.items():
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        for cell_addr, directive in cell_map.items():
            if cell_addr.endswith("_format"):
                base = cell_addr[: -len("_format")]
                try:
                    ws[base] = directive.format(**fmt_args)
                    written += 1
                except Exception:
                    pass
            elif directive == "$company.name":
                try:
                    ws[cell_addr] = company_name
                    written += 1
                except Exception:
                    pass
    return written


def _write_signature_blocks(wb: Workbook, items: list, data: dict) -> int:
    """Fill auditor firm/partner/membership/place/date across all signature blocks."""
    written = 0
    for item in items or []:
        sheet = item.get("sheet")
        cell = item.get("cell")
        path = item.get("json_path")
        if not sheet or sheet not in wb.sheetnames or not cell or not path:
            continue
        v = _get(data, path)
        if v is None or v == "":
            continue
        text = f"{item.get('prefix','')}{v}{item.get('suffix','')}"
        try:
            wb[sheet][cell] = text
            written += 1
        except Exception:
            pass
    return written


def _write_director_signatures(wb: Workbook, items: list, data: dict) -> int:
    """Fill director name + DIN pairs in signature blocks across multiple sheets."""
    directors = data.get("directors") or []
    written = 0
    for item in items or []:
        sheet = item.get("sheet")
        idx = item.get("index", 0)
        if sheet not in wb.sheetnames or idx >= len(directors):
            continue
        d = directors[idx]
        if not isinstance(d, dict):
            continue
        name = d.get("name")
        din = d.get("din")
        ws = wb[sheet]
        if name and item.get("name_cell"):
            try:
                ws[item["name_cell"]] = name
                written += 1
            except Exception:
                pass
        if din and item.get("din_cell"):
            try:
                ws[item["din_cell"]] = f"DIN: {din}"
                written += 1
            except Exception:
                pass
    return written


def _write_simple_mapping(ws, cell_map: dict, data: dict) -> int:
    """Write JSON-path values to specific cells. Skips empties (leaves cell blank)."""
    written = 0
    for cell_addr, json_path in cell_map.items():
        if not isinstance(json_path, str) or json_path.startswith("$"):
            continue
        v = _get(data, json_path)
        if v is None or v == "":
            continue   # leave cell blank — the template's empty state stays
        try:
            ws[cell_addr] = v
            written += 1
        except Exception as exc:
            logger.warning(f"Could not write {cell_addr}={v!r}: {exc}")
    return written


def _write_shareholder_rows(wb: Workbook, descriptor: dict, data: dict) -> int:
    """Fill the shareholder block (Notes sheet starting at row 14)."""
    sheet_name = descriptor.get("sheet")
    start_row = descriptor.get("start_row", 1)
    col_map: dict[str, str] = descriptor.get("columns", {}) or {}
    if not sheet_name or sheet_name not in wb.sheetnames:
        return 0
    ws = wb[sheet_name]
    shareholders = data.get("shareholders") or []
    written = 0
    for i, sh in enumerate(shareholders):
        if not isinstance(sh, dict):
            continue
        row = start_row + i
        for col_letter, key in col_map.items():
            v = sh.get(key)
            if v is not None and v != "":
                try:
                    ws[f"{col_letter}{row}"] = v
                    written += 1
                except Exception:
                    pass
    return written


def _write_director_rows(wb: Workbook, descriptor: dict, data: dict) -> int:
    sheet_name = descriptor.get("sheet")
    start_row = descriptor.get("start_row", 1)
    col_map: dict[str, str] = descriptor.get("columns", {}) or {}
    if not sheet_name or sheet_name not in wb.sheetnames:
        return 0
    ws = wb[sheet_name]
    directors = data.get("directors") or []
    written = 0
    for i, d in enumerate(directors):
        if not isinstance(d, dict):
            continue
        row = start_row + i
        for col_letter, key in col_map.items():
            v = d.get(key)
            if v is not None and v != "":
                try:
                    ws[f"{col_letter}{row}"] = v
                    written += 1
                except Exception:
                    pass
    return written


def _write_auditor_block(wb: Workbook, items: list, data: dict) -> int:
    written = 0
    for item in items or []:
        sheet = item.get("sheet")
        cell = item.get("cell")
        json_path = item.get("json_path")
        prefix = item.get("prefix", "")
        if not sheet or sheet not in wb.sheetnames or not cell:
            continue
        ws = wb[sheet]
        if json_path == "$literal":
            v = item.get("value", "")
        else:
            v = _get(data, json_path)
        if v is None or v == "":
            continue
        try:
            ws[cell] = f"{prefix}{v}" if prefix else v
            written += 1
        except Exception:
            pass
    return written


# ── public API ───────────────────────────────────────────────────────────────

def generate_excel(data: dict, filename_base: str = "tawthiq_xbrl") -> ExcelResult:
    """Build the Excel by loading the template and applying the mapping."""
    try:
        if not TEMPLATE_PATH.exists():
            return ExcelResult(success=False, error=f"Template not found at {TEMPLATE_PATH}")
        if not MAPPING_PATH.exists():
            return ExcelResult(success=False, error=f"Mapping not found at {MAPPING_PATH}")

        with open(MAPPING_PATH, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}

        wb = load_workbook(TEMPLATE_PATH)

        cells_written = 0

        # 1. Title overrides (company name, dates)
        cells_written += _apply_title_overrides(wb, data, mapping.get("title_overrides", {}))

        # 2. Per-sheet simple cell mappings (BS, P&L, CFS, Notes)
        for sheet_name in ("BS", "P&L", "CFS", "Notes"):
            cell_map = mapping.get(sheet_name)
            if not cell_map or sheet_name not in wb.sheetnames:
                continue
            cells_written += _write_simple_mapping(wb[sheet_name], cell_map, data)

        # 3. Dynamic arrays
        if "shareholder_rows" in mapping:
            cells_written += _write_shareholder_rows(wb, mapping["shareholder_rows"], data)
        if "director_rows" in mapping:
            cells_written += _write_director_rows(wb, mapping["director_rows"], data)

        # 4. Auditor signature blocks across all sheets
        if "signature_blocks" in mapping:
            cells_written += _write_signature_blocks(wb, mapping["signature_blocks"], data)

        # 5. Director name + DIN signature blocks across all sheets
        if "director_signatures" in mapping:
            cells_written += _write_director_signatures(wb, mapping["director_signatures"], data)

        # 6. Back-compat: legacy 'auditor' block (used by older mappings)
        if "auditor" in mapping:
            cells_written += _write_auditor_block(wb, mapping["auditor"], data)

        # 7. Save
        buf = io.BytesIO()
        wb.save(buf)
        xlsx_bytes = buf.getvalue()

        # Filename: COMPANY_FY.xlsx
        co_raw = (_get(data, "company.name") or "company").upper()
        co = "".join(c if c.isalnum() else "_" for c in co_raw).strip("_")[:60]
        end = _get(data, "reporting_period.end_date") or ""
        start = _get(data, "reporting_period.start_date") or ""
        try:
            fy = f"{start[:4]}_{end[2:4]}"
        except Exception:
            fy = (end or "FY").replace("-", "_")
        filename = f"{filename_base}_{co}_{fy}.xlsx"

        return ExcelResult(
            success=True,
            xlsx_bytes=xlsx_bytes,
            filename=filename,
            sheet_count=len(wb.worksheets),
            cells_written=cells_written,
        )
    except Exception as exc:
        logger.exception("Excel generation failed")
        return ExcelResult(success=False, error=str(exc))
