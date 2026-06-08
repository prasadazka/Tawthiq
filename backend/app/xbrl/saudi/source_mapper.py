"""Resolve Saudi-IFRS taxonomy concepts from extracted PDF data.

Pure-Python step in the XBRL pipeline. No Gemini calls here — only direct
and synonym lookups. The AI fallback for unmatched line items lives in a
separate module (xbrl/saudi/ai_fallback.py — chunk #2).

INPUT:
    rules_json   : the response from POST /api/validate (rule_results + evidence)
    tables_json  : the response from POST /api/pdf-tables/extract
    taxonomy     : Taxonomy instance (from taxonomy_loader.default_taxonomy())

OUTPUT:
    ResolvedFactSet — every taxonomy concept resolved to either:
        - a value (numeric or text) with provenance, OR
        - status="missing" with a reason
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.xbrl.saudi.taxonomy_loader import Concept, Taxonomy, NON_TAG_VALUES


# Concepts whose value lives in PDF body text — found via the rules engine.
TEXT_CONCEPTS = {
    "Company Name",
    "CR Number",
    "Auditor Name",
    "Audit Opinion",
    "Consolidated Financial Statements",
    "Unified Number",
    "Auditor License Number",
    "SAMA License Number",
}

# Concepts that are not data lookups at all — XBRL artifacts.
ARTIFACT_CONCEPTS = {
    "Reporting Period Start",   # → xbrli:context
    "Reporting Period End",     # → xbrli:context
    "Currency",                 # → xbrli:unit
}


@dataclass
class ResolvedFact:
    business_term: str
    xbrl_tag: str
    section_id: str
    status: str  # "found" | "missing" | "artifact"
    source: Optional[str] = None  # "tables" | "rules" | None
    value_cy: Any = None
    value_py: Any = None
    currency: Optional[str] = None
    evidence: Optional[str] = None
    page: Optional[int] = None
    matched_via: Optional[str] = None  # "canonical" | "synonym"
    reason: Optional[str] = None       # populated when status="missing"


@dataclass
class ResolvedFactSet:
    facts: list[ResolvedFact] = field(default_factory=list)

    def by_term(self, term: str) -> Optional[ResolvedFact]:
        return next((f for f in self.facts if f.business_term == term), None)

    def by_section(self, section_id: str) -> list[ResolvedFact]:
        return [f for f in self.facts if f.section_id == section_id]

    def found(self) -> list[ResolvedFact]:
        return [f for f in self.facts if f.status == "found"]

    def missing(self) -> list[ResolvedFact]:
        return [f for f in self.facts if f.status == "missing"]

    def artifacts(self) -> list[ResolvedFact]:
        return [f for f in self.facts if f.status == "artifact"]

    @property
    def coverage_pct(self) -> float:
        data_facts = [f for f in self.facts if f.status != "artifact"]
        if not data_facts:
            return 0.0
        return round(100 * len(self.found()) / len(data_facts), 1)


def _normalize(s: str) -> str:
    """Aggressive normalization so 'Property, plant and equipment' matches
    'Property Plant Equipment'. Strips punctuation, normalises &/and,
    collapses whitespace, lowercases."""
    s = s.strip().lower()
    s = s.replace("&", " and ")
    # Strip common punctuation
    s = re.sub(r"[,;:.\-\(\)\[\]\"'`]", " ", s)
    # Drop trivially-filler words to make matches more forgiving
    s = re.sub(r"\b(the|of|in|on|at|for)\b", " ", s)
    return " ".join(s.split())


def _is_year_column(name: str) -> bool:
    n = str(name)
    nl = n.lower()
    # English/numeric year markers
    if any(k in nl for k in ["2023", "2024", "2025", "2026", "december", "march"]):
        return True
    # Arabic
    if any(c in n for c in ["ديسمبر", "يناير", "مارس"]):
        return True
    if any(c in n for c in ["٢٠٢", "۲۰۲"]):
        return True
    return False


def _classify_year_columns(year_cols: list[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (cy_col, py_col). Heuristic: pick the column with the largest
    visible year as CY, the other (if any) as PY."""
    if not year_cols:
        return None, None
    if len(year_cols) == 1:
        return year_cols[0], None

    def year_of(name: str) -> int:
        # Try ASCII digits first
        m = re.search(r"(20\d{2})", name)
        if m:
            return int(m.group(1))
        # Arabic-Indic digits
        ar_digits = name.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        m = re.search(r"(20\d{2})", ar_digits)
        return int(m.group(1)) if m else 0

    sorted_cols = sorted(year_cols, key=year_of, reverse=True)
    return sorted_cols[0], sorted_cols[1]


# ── table-side lookup ────────────────────────────────────────────────────────

# For each taxonomy section, the table title-keyword(s) that signal "this
# is the right primary statement to look in". Used to prefer the correct
# table when a line item name appears in more than one place (e.g. Trade
# Receivables shows up in the Balance Sheet AND in the Cash Flow's working-
# capital changes section).
SECTION_TITLE_HINTS = {
    "balance_sheet": ["financial position", "balance sheet", "المركز المالي"],
    "income_statement": ["profit or loss", "income statement", "p&l", "الدخل", "الربح أو الخسارة"],
    "cash_flow": ["cash flow", "cash flows", "التدفقات النقدية"],
    "changes_in_equity": ["changes in equity", "equity", "التغيرات في حقوق"],
}


def _table_matches_section(table: dict, section_id: str) -> bool:
    hints = SECTION_TITLE_HINTS.get(section_id, [])
    if not hints:
        return False
    title = (table.get("title_as_printed") or table.get("target_title") or "").lower()
    return any(h in title for h in hints)


def _iter_table_rows(
    tables_json: dict, prefer_section: Optional[str] = None, strict: bool = False,
) -> Iterable[tuple[dict, dict]]:
    """Yield (table, row) for every row in every table with data.

    If `prefer_section` is set, the matching primary-statement tables are
    yielded FIRST. If `strict=True`, ONLY matching-section tables are
    yielded — used for primary-statement concepts to prevent grabbing
    e.g. a Trade Receivables row from the Cash Flow's working-capital
    adjustments instead of the Balance Sheet.
    """
    tables = [t for t in tables_json.get("tables", []) if t.get("found")]

    if prefer_section:
        preferred = [t for t in tables if _table_matches_section(t, prefer_section)]
        if strict:
            tables = preferred
        else:
            rest = [t for t in tables if not _table_matches_section(t, prefer_section)]
            tables = preferred + rest

    for table in tables:
        for row in table.get("rows") or []:
            yield table, row


def _lookup_concept_in_tables(
    concept: Concept,
    tables_json: dict,
    taxonomy: Taxonomy,
) -> Optional[ResolvedFact]:
    labels_norm = {_normalize(label): label for label in concept.all_labels()}

    # Primary-statement concepts must come from their own primary statement,
    # never from a similarly-named row in a note schedule or another statement.
    strict = concept.section_id in {
        "balance_sheet", "income_statement", "cash_flow", "changes_in_equity"
    }
    for table, row in _iter_table_rows(
        tables_json, prefer_section=concept.section_id, strict=strict,
    ):
        # find description value
        li = row.get("line_item") or row.get("description")
        if not li or not isinstance(li, str):
            # try first string field
            for k, v in row.items():
                if isinstance(v, str) and not _is_year_column(k):
                    li = v
                    break
        if not li:
            continue
        key = _normalize(li)
        if key not in labels_norm:
            continue

        cols = table.get("columns") or []
        year_cols = [c for c in cols if _is_year_column(c)]
        cy_col, py_col = _classify_year_columns(year_cols)

        cy_val = row.get(cy_col) if cy_col else None
        py_val = row.get(py_col) if py_col else None

        # If both null, this row doesn't carry data for the concept — keep searching
        if cy_val is None and py_val is None:
            continue

        matched_label = labels_norm[key]
        matched_via = "canonical" if matched_label == concept.business_term else "synonym"

        return ResolvedFact(
            business_term=concept.business_term,
            xbrl_tag=concept.xbrl_tag,
            section_id=concept.section_id,
            status="found",
            source="tables",
            value_cy=cy_val,
            value_py=py_val,
            currency=table.get("currency"),
            evidence=li,
            page=table.get("page"),
            matched_via=matched_via,
        )
    return None


# ── rule-side lookup (text concepts) ─────────────────────────────────────────

# Each text concept is extracted from a specific rule's evidence_quotes (NOT
# the AI-written details narrative). Two extraction modes:
#   - "regex"     : pattern run against each evidence_quote; first group wins
#   - "filter"    : function that takes a quote and returns True if it IS the
#                   concept value (e.g. a string that looks like a company name)
TEXT_HINTS = {
    "Company Name": {
        "rule_ids": ["R02", "R23"],
        "filter": lambda q: _looks_like_entity_name(q),
    },
    "CR Number": {
        "rule_ids": ["R02", "R21", "R23"],
        # Saudi CR numbers are 10 digits starting with 10
        "regex": r"\b(10\d{8})\b",
    },
    "Unified Number": {
        "rule_ids": ["R23"],
        # Saudi Unified Number is 10 digits starting with 7
        "regex": r"\b(7\d{9})\b",
    },
    "Auditor Name": {
        "rule_ids": ["R21"],
        "filter": lambda q: _looks_like_auditor_name(q),
    },
    "Auditor License Number": {
        "rule_ids": ["R21"],
        # License / certificate / membership numbers ≥ 4 digits, e.g. "License No. 391"
        "regex": r"(?:license|licence|certificate|membership|registration)\s*(?:no\.?|number)?\s*[:#]?\s*(\d{3,8})",
    },
    "Audit Opinion": {
        "rule_ids": ["R03"],
        "regex": r"\b(unqualified|qualified|adverse|disclaimer)\b",
        "search_details_too": True,
    },
    "Consolidated Financial Statements": {
        "rule_ids": ["R02", "R03"],
        "regex": r"\b(consolidated|standalone)\b",
        "search_details_too": True,
    },
    "SAMA License Number": {
        "rule_ids": [],   # banking-specific; only relevant for bank PDFs
        "regex": r"sama\s*(?:license|licence)[:\s#]*(\d+)",
    },
}

# Words that mark an evidence_quote as a candidate company name
_ENTITY_KEYWORDS_EN = re.compile(
    r"\b(company|group|corporation|holding|sa|saudi|joint\s*stock)\b",
    re.IGNORECASE,
)
_ENTITY_KEYWORDS_AR = re.compile(r"شركة|مجموعة|مساهمة")

# Auditor firm name keywords
_AUDITOR_KEYWORDS = re.compile(
    r"(?:for\s+)?\b(ernst\s*[&\s]*young|kpmg|deloitte|pricewaterhousecoopers|pwc|grant\s*thornton|bdo|baker\s*tilly|crowe|al\s*kharashi|kpmg\s*al\s*fozan|kbig)\b",
    re.IGNORECASE,
)


def _looks_like_entity_name(quote: str) -> bool:
    if not quote or not isinstance(quote, str):
        return False
    s = quote.strip()
    if len(s) < 6 or len(s) > 200:
        return False
    # Reject obvious non-names
    if re.search(r"\b(article|note|page|opinion|standard)\b", s, re.IGNORECASE):
        return False
    return bool(_ENTITY_KEYWORDS_EN.search(s) or _ENTITY_KEYWORDS_AR.search(s))


def _looks_like_auditor_name(quote: str) -> bool:
    if not quote or not isinstance(quote, str):
        return False
    s = quote.strip()
    if len(s) < 4 or len(s) > 150:
        return False
    return bool(_AUDITOR_KEYWORDS.search(s))


def _clean_value(value: str) -> str:
    s = (value or "").strip().strip('"\'')
    # Strip surrounding parens used for translation aside
    s = re.sub(r"\s*\([^)]{3,}\)\s*$", "", s)
    return s


# Arabic-Indic digits → Latin so regex like \b(10\d{8})\b works on Arabic PDFs.
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _to_latin_digits(s: str) -> str:
    return s.translate(_ARABIC_DIGITS) if s else s


def _strip_digit_punct(s: str) -> str:
    """Remove dots / hyphens / spaces between digits so '١٠١.٢٠٣٨٩٦' becomes
    '101203896' before the regex looks for a 10-digit Saudi CR."""
    return re.sub(r"(?<=\d)[\s.\-,](?=\d)", "", s)


def _lookup_concept_in_rules(
    concept: Concept, rules_json: dict
) -> Optional[ResolvedFact]:
    hint = TEXT_HINTS.get(concept.business_term)
    if not hint:
        return None
    rule_results = rules_json.get("results") or []
    candidate_rules = (
        [r for r in rule_results if r.get("rule_id") in hint["rule_ids"]]
        if hint["rule_ids"] else rule_results
    )

    filter_fn = hint.get("filter")
    regex = hint.get("regex")
    search_details = hint.get("search_details_too", False)

    for rule in candidate_rules:
        quotes = [q for q in (rule.get("evidence_quotes") or []) if isinstance(q, str)]
        haystacks = list(quotes)
        if search_details:
            details = rule.get("details") or ""
            if isinstance(details, str):
                haystacks.append(details)

        # Filter mode: pick the first quote that passes the filter
        if filter_fn:
            for q in quotes:
                if filter_fn(q):
                    page = None
                    locs = rule.get("locations") or []
                    if locs and isinstance(locs[0], dict):
                        page = locs[0].get("page")
                    return ResolvedFact(
                        business_term=concept.business_term,
                        xbrl_tag=concept.xbrl_tag,
                        section_id=concept.section_id,
                        status="found",
                        source="rules",
                        value_cy=_clean_value(q),
                        evidence=q[:200],
                        page=page,
                        matched_via=f"rule:{rule.get('rule_id')}",
                    )

        # Regex mode: try each haystack (with Arabic-Indic → Latin normalization
        # and inter-digit punctuation stripped for ID-like patterns)
        if regex:
            for raw_hay in haystacks:
                hay = _strip_digit_punct(_to_latin_digits(raw_hay))
                m = re.search(regex, hay, re.IGNORECASE)
                if not m:
                    continue
                value = m.group(1) if m.groups() else m.group(0)
                page = None
                locs = rule.get("locations") or []
                if locs and isinstance(locs[0], dict):
                    page = locs[0].get("page")
                return ResolvedFact(
                    business_term=concept.business_term,
                    xbrl_tag=concept.xbrl_tag,
                    section_id=concept.section_id,
                    status="found",
                    source="rules",
                    value_cy=_clean_value(value),
                    evidence=hay[:200],
                    page=page,
                    matched_via=f"rule:{rule.get('rule_id')}",
                )
    return None


# ── orchestration ────────────────────────────────────────────────────────────

def map_concepts(
    rules_json: dict,
    tables_json: dict,
    taxonomy: Taxonomy,
) -> ResolvedFactSet:
    facts: list[ResolvedFact] = []
    for concept in taxonomy.all_concepts():
        # XBRL artifacts (Context / Unit / Local Extension)
        if not concept.is_real_tag:
            if concept.business_term in ARTIFACT_CONCEPTS:
                facts.append(ResolvedFact(
                    business_term=concept.business_term,
                    xbrl_tag=concept.xbrl_tag,
                    section_id=concept.section_id,
                    status="artifact",
                    reason="XBRL artifact — derived during XBRL emission",
                ))
                continue
            # "Local Extension" — text concept, try rules
        # Text concept → search rule results
        if concept.business_term in TEXT_CONCEPTS:
            f = _lookup_concept_in_rules(concept, rules_json)
            facts.append(f or ResolvedFact(
                business_term=concept.business_term,
                xbrl_tag=concept.xbrl_tag,
                section_id=concept.section_id,
                status="missing",
                reason="not found in rule_results",
            ))
            continue
        # Default: numeric concept → search tables JSON
        f = _lookup_concept_in_tables(concept, tables_json, taxonomy)
        facts.append(f or ResolvedFact(
            business_term=concept.business_term,
            xbrl_tag=concept.xbrl_tag,
            section_id=concept.section_id,
            status="missing",
            reason="no matching line item via direct or synonym",
        ))
    return ResolvedFactSet(facts=facts)
