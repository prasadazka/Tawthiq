import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from app.rules.registry import Rule, ValidationType
from app.services.extractor import query_with_gemini

logger = logging.getLogger(__name__)


@dataclass
class RuleResult:
    rule_id: str
    rule_name: str
    description: str
    status: str  # pass, fail, skip, error
    details: str
    severity: str
    locations: list[dict] = field(default_factory=list)


def _find_keyword_locations(pages: list[dict], keywords: list[str], max_pages: int = 5) -> list[dict]:
    """Find which pages/paragraphs contain matched keywords. Returns up to max_pages locations."""
    locations = []
    for page in pages:
        page_bboxes = []
        for para in page.get("paragraphs", []):
            para_lower = para["text"].lower()
            if any(kw.lower() in para_lower for kw in keywords):
                if para["bounding_box"]["vertices"]:
                    page_bboxes.append(para["bounding_box"])
        if page_bboxes:
            locations.append({
                "page": page["page_number"],
                "bounding_boxes": page_bboxes,
            })
            if len(locations) >= max_pages:
                break
    return locations


def _check_with_docai(doc_data: dict, rule: Rule) -> RuleResult:
    """Check rule against Document AI extracted text (deterministic keyword search)."""
    text = doc_data["full_text"].lower()
    found = [kw for kw in rule.keywords if kw.lower() in text]
    locations = _find_keyword_locations(doc_data.get("pages", []), found) if found else []
    if found:
        return RuleResult(
            rule_id=rule.id, rule_name=rule.name, description=rule.description,
            status="pass", details=f"Found in document: {', '.join(found)}",
            severity=rule.severity.value,
            locations=locations,
        )
    return RuleResult(
        rule_id=rule.id, rule_name=rule.name, description=rule.description,
        status="fail", details=f"Not found in OCR text. Searched: {rule.keywords}",
        severity=rule.severity.value,
    )


def _check_with_gemini(pdf_bytes: bytes, rule: Rule) -> RuleResult:
    """Send PDF directly to Gemini for AI-based validation."""
    prompt = f"""You are a financial document validator.

RULE: {rule.name}
DESCRIPTION: {rule.description}

TASK: {rule.ai_prompt}

IMPORTANT: Respond in this exact JSON format:
{{"result": "PASS" or "FAIL", "evidence": "what you found", "details": "explanation", "pages": [list of 1-indexed page numbers where evidence was found, e.g. [1, 3, 5]]}}

Only return the JSON, nothing else."""

    try:
        response = query_with_gemini(pdf_bytes, prompt)
        # Clean markdown fences if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        status = "pass" if data.get("result", "").upper() == "PASS" else "fail"
        details = f"{data.get('evidence', '')} | {data.get('details', '')}"

        # Extract page locations from Gemini response
        gemini_pages = data.get("pages", [])
        locations = [
            {"page": p, "bounding_boxes": []}
            for p in gemini_pages if isinstance(p, int)
        ]

        return RuleResult(
            rule_id=rule.id, rule_name=rule.name, description=rule.description,
            status=status, details=details.strip(" |"),
            severity=rule.severity.value,
            locations=locations,
        )
    except json.JSONDecodeError:
        # Fallback: parse raw text
        response_lower = response.lower()
        has_pass = '"pass"' in response_lower or "'pass'" in response_lower
        return RuleResult(
            rule_id=rule.id, rule_name=rule.name, description=rule.description,
            status="pass" if has_pass else "fail",
            details=response.strip()[:500],
            severity=rule.severity.value,
        )
    except Exception as e:
        return RuleResult(
            rule_id=rule.id, rule_name=rule.name, description=rule.description,
            status="error", details=f"AI validation failed: {str(e)}",
            severity=rule.severity.value,
        )


def _check_hybrid(pdf_bytes: bytes, doc_data: dict, rule: Rule) -> RuleResult:
    """First check Document AI text, if inconclusive fall back to Gemini."""
    if rule.keywords:
        docai_result = _check_with_docai(doc_data, rule)
        if docai_result.status == "pass":
            return docai_result
    # Fall through to Gemini for deeper analysis
    if rule.ai_prompt:
        return _check_with_gemini(pdf_bytes, rule)
    return _check_with_docai(doc_data, rule)


def run_rules(
    pdf_bytes: bytes,
    doc_data: dict,
    sector: str,
    metadata: Optional[dict] = None,
) -> list[dict]:
    from app.rules.registry import get_rules

    applicable_rules = get_rules(sector)

    # Phase 1: Run fast DocAI-based rules synchronously and collect Gemini tasks
    results_map: dict[str, RuleResult] = {}
    gemini_tasks: list[tuple[str, Rule]] = []  # (rule_id, rule)

    for rule in applicable_rules:
        if rule.id == "R19":
            results_map[rule.id] = RuleResult(
                rule_id=rule.id, rule_name=rule.name, description=rule.description,
                status="skip", details="Meta-rule: validated through other individual rules",
                severity=rule.severity.value,
            )
            continue

        if rule.validation_type == ValidationType.PRESENCE_CHECK:
            # Try DocAI first; if pass, done. If fail, need Gemini fallback.
            if rule.keywords:
                docai_result = _check_with_docai(doc_data, rule)
                if docai_result.status == "pass":
                    results_map[rule.id] = docai_result
                    continue
            # Need Gemini fallback
            if rule.ai_prompt:
                gemini_tasks.append(("gemini", rule))
            else:
                results_map[rule.id] = _check_with_docai(doc_data, rule)
            continue

        elif rule.validation_type == ValidationType.PATTERN_MATCH:
            results_map[rule.id] = _check_with_docai(doc_data, rule)

        elif rule.validation_type == ValidationType.AI_JUDGMENT:
            gemini_tasks.append(("gemini", rule))

        elif rule.validation_type == ValidationType.FIELD_EXTRACTION:
            # Hybrid: try DocAI first
            if rule.keywords:
                docai_result = _check_with_docai(doc_data, rule)
                if docai_result.status == "pass":
                    results_map[rule.id] = docai_result
                    continue
            if rule.ai_prompt:
                gemini_tasks.append(("gemini", rule))
            else:
                results_map[rule.id] = _check_with_docai(doc_data, rule)

        elif rule.validation_type == ValidationType.CONDITIONAL:
            results_map[rule.id] = RuleResult(
                rule_id=rule.id, rule_name=rule.name, description=rule.description,
                status="skip", details="Requires initial form data for comparison",
                severity=rule.severity.value,
            )
        else:
            results_map[rule.id] = RuleResult(
                rule_id=rule.id, rule_name=rule.name, description=rule.description,
                status="skip", details="Validation type not implemented",
                severity=rule.severity.value,
            )

    # Phase 2: Run all Gemini calls in parallel
    if gemini_tasks:
        logger.info(f"Running {len(gemini_tasks)} Gemini rules in parallel: "
                     f"{[r.id for _, r in gemini_tasks]}")
        with ThreadPoolExecutor(max_workers=len(gemini_tasks)) as executor:
            futures = {
                executor.submit(_check_with_gemini, pdf_bytes, rule): rule
                for _, rule in gemini_tasks
            }
            for future in as_completed(futures):
                rule = futures[future]
                try:
                    result = future.result()
                    results_map[rule.id] = result
                except Exception as e:
                    results_map[rule.id] = RuleResult(
                        rule_id=rule.id, rule_name=rule.name, description=rule.description,
                        status="error", details=f"AI validation failed: {str(e)}",
                        severity=rule.severity.value,
                    )

    # Return results in original rule order
    ordered_results = []
    for rule in applicable_rules:
        if rule.id in results_map:
            ordered_results.append(results_map[rule.id])

    return [
        {
            "rule_id": r.rule_id,
            "rule_name": r.rule_name,
            "description": r.description,
            "status": r.status,
            "details": r.details,
            "severity": r.severity,
            "locations": r.locations,
        }
        for r in ordered_results
    ]
