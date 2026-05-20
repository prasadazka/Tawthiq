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

CIN (Corporate Identification Number, 21-character MCA identifier):
- Format: [U|L|C] + 5-digit industry code + 2-letter state code + 4-digit year + [PTC|PLC|GOI|...] + 6-digit sequence
- Example shape only (do NOT return this value): U#####XX####XXX######
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
- DIN format: exactly 8 numeric digits. Often labelled "DIN:" or "(DIN-########)"
  near the director's printed name in the signature block.

INDUSTRY TYPE — MUST MAP business description to one of these MCA classifications:
- "Commercial and Industrial" → Use for ALL trading, retail, manufacturing, services, jewellery,
  garments, electronics, FMCG, real estate, IT, telecom, hospitality, healthcare, education, etc.
  (This is the catch-all for non-financial businesses.)
- "Banking" → Banks, scheduled commercial banks, cooperative banks
- "NBFC" → Non-Banking Financial Companies, lending companies, housing finance
- "Insurance" → Life or general insurance companies
- "Power" → Electricity generation, transmission, distribution, renewable energy
DO NOT output the business activity itself (e.g., "Jewellery Retail" is WRONG — use "Commercial and Industrial").

CRITICAL — COMPARATIVE PRIOR YEAR VALUES (MANDATORY):
Every Indian Balance Sheet / Profit & Loss / Cash Flow Statement has TWO numeric columns:
the current year (CY) and the prior year (PY) shown side-by-side for comparison.

You MUST extract BOTH years for every numeric line item:
  - balance_sheet.current_year.* AND balance_sheet.prior_year.*
  - profit_loss.current_year.* AND profit_loss.prior_year.*

How to find prior year on the Balance Sheet:
  - The column immediately to the right of the current-year amount is almost always prior year.
  - Column header reads "As at 31 March 2022" (or whichever year is one before current).
  - If you see "31-03-2023" and "31-03-2022" headers, the 2023 numbers go to current_year,
    the 2022 numbers go to prior_year.

How to find prior year on P&L:
  - Same two-column layout — "Year ended 31-03-2023" and "Year ended 31-03-2022".

For EVERY balance sheet line (Share Capital, Reserves, Borrowings, Trade Payables,
Tangible Assets, Inventories, Trade Receivables, Cash, etc.) and EVERY P&L line (Revenue,
Expenses, Profit Before Tax, Tax, Profit for the Period), populate the prior_year object
fully — do NOT leave it as null/empty when the value is clearly printed in the document.

If a particular line truly has no prior year column (rare — e.g., a first-year company),
explicitly set the prior_year field to 0, not null. Null means "I did not find this" —
reserve that for fields that genuinely aren't in the PDF.

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

DETAILED NOTES SECTIONS — These are MANDATORY for Indian XBRL filings. Search the
notes section of the PDF for these specific tables and extract every row:

1. PROPERTY, PLANT & EQUIPMENT MOVEMENT TABLE (Note 7 in most Indian filings):
   - This is a wide table with multiple asset classes as rows and movement columns:
     Gross Block (Opening, Additions, Deletions, Closing) | Depreciation (Opening, For Year, Adjustments, Closing) | Net Block (CY, PY)
   - Asset classes seen in practice: "Computers and Data Processing Units", "Plant and
     Machinery", "Office Equipment", "Furniture and Fixtures", "Vehicles", "Land",
     "Buildings". Use the closest matching enum value from the schema.
   - Extract EVERY row, plus the totals row.
   - Values are typically shown in thousands — multiply by 1000 if the table header
     says "in thousands" or "₹ '000".

2. RELATED PARTY TRANSACTIONS TABLE (Note 22):
   - Three sub-sections typically:
     22.1 Key Managerial Personnel list (name + relation, e.g., "G Krishna — Director")
     22.2 Directors interested in concerns (other entities where directors have stake)
     22.3 Transactions table: rows of [Name, Loan Accepted, Loan Repaid, Year End
          Balance, Remuneration Paid]
   - For 22.3, populate the `related_parties[]` array with one entry per person.
   - Relationship = "Key Managerial Personnel" for KMP, "Director" for board directors.

3. TRADE PAYABLES AGING (Schedule III mandatory):
   - Buckets: < 1 year, 1-2 years, 2-3 years, > 3 years.
   - Categories: (i) MSME, (ii) Others, (iii) Disputed dues MSME, (iv) Disputed
     Dues Others.
   - Extract for BOTH years (CY and PY tables).
   - Fields not present in PDF → use 0 (don't leave null).

4. TRADE RECEIVABLES AGING (Schedule III mandatory):
   - Buckets: < 6 months, 6 months-1 year, 1-2 years, 2-3 years, > 3 years.
   - Categories: Undisputed Good, Undisputed Doubtful, Disputed Good, Disputed
     Doubtful.

5. SHARE CAPITAL RECONCILIATION (Note 2.2):
   - Table showing: Equity shares at beginning + Issued during year - Bought back
     during year = Equity shares at end.
   - Extract for BOTH CY and PY.

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
        """Recursively turn schema nodes into NEUTRAL type-shaped placeholders.

        We deliberately IGNORE the `example:` field from the YAML — those examples
        are documentation only. Including real values in the prompt would bias
        Gemini toward those values for any uploaded PDF. The placeholders here
        only convey TYPE and SHAPE.
        """
        if not isinstance(node, dict):
            return node

        # Leaf field with type info
        if "type" in node and not any(isinstance(v, dict) for v in node.values()):
            t = node.get("type")
            # NOTE: 'example' from YAML is intentionally NOT used here — bias risk.
            if t == "string":
                return "<string from PDF>"
            if t == "number":
                return "<number>"
            if t == "date":
                return "<YYYY-MM-DD>"
            if t == "boolean":
                return "<true/false>"
            if t == "enum":
                allowed = node.get("enum", [])
                return f"<one of: {allowed}>"
            if t == "array":
                return []
            return None

        # Array node with items definition
        if node.get("type") == "array" and "items" in node:
            return [self._field_to_example(node["items"])]

        # Nested object — recurse, skip metadata keys
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
