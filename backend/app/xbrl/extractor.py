"""Generic XBRL data extractor.

Loads a country-specific extraction_schema.yml, builds a Gemini prompt that
describes the expected JSON structure, sends the PDF to Gemini, and returns
parsed JSON ready for the validator + XBRL generator.

Adding a new country = new extraction_schema.yml. No code change needed.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.services.extractor import query_llm

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    success: bool
    data: dict = field(default_factory=dict)
    error: str = ""
    raw_response: str = ""


class XBRLDataExtractor:
    """Extract structured JSON from a PDF using Gemini, guided by a schema YAML."""

    def __init__(self, schema_path: str | Path):
        with open(schema_path, "r", encoding="utf-8") as f:
            self.schema = yaml.safe_load(f)
        self.country = self.schema.get("country", "unknown")

    # ── public API ────────────────────────────────────────────────────────────

    def extract(self, pdf_bytes: bytes, document_text: str = "") -> ExtractionResult:
        """Run Gemini against the PDF using the schema as a structure guide."""
        prompt = self._build_prompt()
        try:
            raw = query_llm(prompt, document_text, pdf_bytes)
        except Exception as exc:
            return ExtractionResult(success=False, error=f"LLM call failed: {exc}")

        try:
            data = self._parse_json(raw)
        except json.JSONDecodeError as exc:
            return ExtractionResult(
                success=False, error=f"JSON parse failed: {exc}", raw_response=raw[:1000]
            )

        if not isinstance(data, dict):
            return ExtractionResult(
                success=False, error="LLM did not return a JSON object", raw_response=raw[:1000]
            )

        return ExtractionResult(success=True, data=data, raw_response=raw)

    # ── prompt construction ──────────────────────────────────────────────────

    def _build_prompt(self) -> str:
        """Convert schema into a concise structured prompt for Gemini."""
        skeleton = self._build_json_skeleton(self.schema)
        country_name = self.country.capitalize()
        return f"""You are extracting structured financial data from a {country_name} company annual report PDF for XBRL generation.

TASK: Read the entire PDF carefully (including page 1, audit report, all notes, signature blocks) and produce a single JSON object that EXACTLY matches the schema below.

CRITICAL RULES:
1. Output ONLY valid JSON — no markdown fences, no explanations, no preamble.
2. Use the EXACT field names from the schema (snake_case, case-sensitive).
3. For dates use ISO format: YYYY-MM-DD.
4. For numeric financial values: output absolute values in the document's currency unit. If the report says "in thousands", multiply by 1000 to get absolute rupees. If "in lakhs" multiply by 100000. If "in crores" multiply by 10000000. The "Actual" rounding level means use the numbers as printed.
5. For enum fields, choose ONLY from the allowed values listed in the schema.
6. If a field is genuinely not present in the document, use null. Do NOT invent or guess data.
7. For dimensional arrays (shareholders, directors, property_plant_equipment), include ALL items found in the document.
8. Negative values (losses, decreases) must be negative numbers, not strings.

WHERE TO FIND CRITICAL FIELDS — SEARCH EVERY PAGE:

CIN (Corporate Identification Number, 21 characters, format like U52393TG2011PTC072492):
- Look on the cover page or first page of the document
- Look in the auditor's report header/letterhead (often appears alongside the company name)
- Look in Note 1 "Corporate Information" or "Organisation and Activities"
- Look at the bottom of the Balance Sheet under company signature block
- Look on the directors' report letterhead
- The CIN is mandatory in every Indian filing — it MUST be present somewhere

REGISTERED OFFICE ADDRESS:
- Look in Note 1 "Corporate Information" (it almost always lists the registered office)
- Look in the auditor's report addressee line ("To the Members of [Company]" usually precedes address)
- Look in the company letterhead at top of cover page
- Look at the signature block on the balance sheet ("Place: Hyderabad", "Date: ...")
- Combine street, area, city, state code, PIN code into a single address string

DIRECTORS — STRICT RULES (very important to avoid false directors):
- A director is ONLY someone whose name appears with the word "Director" or "Managing Director"
  in the signature block of the Balance Sheet, the Directors' Report, or the Board Report.
- Shareholders listed in the share-capital note are NOT directors unless they ALSO appear
  with a Director title in a signature block.
- If the balance sheet signature block shows 2 director signatures, then there are 2 directors —
  do NOT add other names from elsewhere in the document.
- Each director MUST have an 8-digit DIN. If you cannot find a DIN near a director's name,
  do NOT include that person in the directors array.
- DIN format: exactly 8 numeric digits (e.g., 03363685, 00112233). Often labelled "DIN:" or
  "(DIN-12345678)" near the director's printed name in the signature block.

INDUSTRY TYPE — MUST MAP business description to one of these MCA classifications:
- "Commercial and Industrial" → Use for ALL trading, retail, manufacturing, services, jewellery,
  garments, electronics, FMCG, real estate, IT, telecom, hospitality, healthcare, education, etc.
  (This is the catch-all for non-financial businesses.)
- "Banking" → Banks, scheduled commercial banks, cooperative banks
- "NBFC" → Non-Banking Financial Companies, lending companies, housing finance
- "Insurance" → Life or general insurance companies
- "Power" → Electricity generation, transmission, distribution, renewable energy
DO NOT output the business activity itself (e.g., "Jewellery Retail" is WRONG — use "Commercial and Industrial").

EXTRACTION TARGETS:
- Company identity (name, CIN, registered address, industry, PAN, type)
- Reporting period (current and prior year dates, report type, level of rounding, cash flow method)
- Balance Sheet (current AND prior year — all asset/liability/equity line items)
- Profit & Loss (current AND prior year — revenue, expenses, profit)
- Cash Flow (current year — operating/investing/financing activities, opening/closing cash)
- Auditor details (firm name, FRN, partner name, membership number, address, signature date, opinion type)
- Directors list (name, DIN, designation, signing role) — search all pages including signature blocks
- Shareholders list (≥5% holders with name, PAN if available, shares, percentage)
- Share capital classes (authorized and issued)
- Property/Plant/Equipment movement schedule (if present)
- Board approval date

JSON SCHEMA SKELETON:
{skeleton}

Return ONLY the populated JSON object now.
"""

    def _build_json_skeleton(self, schema: dict) -> str:
        """Convert the schema YAML into a JSON-skeleton string the LLM can imitate.

        Each field is rendered as a comment showing type/required/example.
        """
        lines: list[str] = []
        # Top-level keys that describe data (skip metadata like schema_version)
        data_keys = [
            "company",
            "reporting_period",
            "balance_sheet",
            "profit_loss",
            "cash_flow",
            "auditor",
            "directors",
            "shareholders",
            "share_capital",
            "property_plant_equipment",
            "board_approval",
            "disclosures",
        ]
        skeleton: dict = {}
        for k in data_keys:
            if k in schema:
                skeleton[k] = self._field_to_example(schema[k])

        return json.dumps(skeleton, indent=2, ensure_ascii=False)

    def _field_to_example(self, node: Any) -> Any:
        """Recursively turn schema nodes into example values for the prompt."""
        if not isinstance(node, dict):
            return node

        # Leaf field with type info
        if "type" in node and not any(isinstance(v, dict) for v in node.values()):
            t = node.get("type")
            ex = node.get("example")
            if ex is not None:
                return ex
            if t == "string":
                return "string"
            if t == "number":
                return 0
            if t == "date":
                return "YYYY-MM-DD"
            if t == "boolean":
                return False
            if t == "enum":
                allowed = node.get("enum", [])
                return f"one of: {allowed}"
            if t == "array":
                return []
            return None

        # Array node with items definition
        if node.get("type") == "array" and "items" in node:
            return [self._field_to_example(node["items"])]

        # Nested object
        out: dict = {}
        for key, sub in node.items():
            if key in {"type", "required", "description", "example", "enum", "pattern", "format", "decimals"}:
                continue
            out[key] = self._field_to_example(sub)
        return out

    # ── JSON parsing ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Strip markdown fences and parse JSON. Tolerates trailing text."""
        text = raw.strip()
        if text.startswith("```"):
            # remove leading fence
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.replace("```json", "").replace("```JSON", "")
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        # Find the first { and last } to be safe
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            text = text[first : last + 1]
        return json.loads(text)
