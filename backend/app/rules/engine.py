import copy
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from app.rules.registry import Rule, ValidationType
from app.services.extractor import query_llm, resolve_evidence_locations

MAX_LLM_WORKERS = 8
LLM_RETRIES = 2
LLM_RETRY_DELAY = 2  # seconds
BATCH_SIZE = 6  # rules per Gemini call

logger = logging.getLogger(__name__)


@dataclass
class RuleResult:
    rule_id: str
    rule_name: str
    description: str
    status: str  # pass, fail, skip, error, not_applicable
    details: str
    severity: str
    locations: list[dict] = field(default_factory=list)


def _parse_llm_json(raw: str) -> dict:
    """Clean markdown fences and parse JSON from LLM response."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def _build_rule_result(rule: Rule, data: dict) -> RuleResult:
    """Build a RuleResult from parsed LLM JSON for a single rule."""
    status = "pass" if data.get("result", "").upper() == "PASS" else "fail"
    details = f"{data.get('evidence', '')} | {data.get('details', '')}"
    llm_pages = data.get("pages", [])
    evidence_quotes = data.get("evidence_quotes", [])
    if not isinstance(evidence_quotes, list):
        evidence_quotes = []
    locations = [
        {"page": p, "bounding_boxes": [], "evidence_quotes": evidence_quotes}
        for p in llm_pages if isinstance(p, int)
    ]
    return RuleResult(
        rule_id=rule.id, rule_name=rule.name, description=rule.description,
        status=status, details=details.strip(" |"),
        severity=rule.severity.value,
        locations=locations,
    )


def _call_llm_with_retry(prompt: str, document_text: str, pdf_bytes: bytes, label: str) -> str:
    """Call LLM with retry logic for rate limits."""
    for attempt in range(LLM_RETRIES):
        try:
            return query_llm(prompt, document_text, pdf_bytes)
        except Exception as err:
            if "429" in str(err) and attempt < LLM_RETRIES - 1:
                wait = LLM_RETRY_DELAY * (attempt + 1)
                logger.warning(f"Rate limited on {label}, retry {attempt+1}/{LLM_RETRIES} in {wait}s")
                time.sleep(wait)
            else:
                raise


def _check_with_llm(pdf_bytes: bytes, doc_data: dict, rule: Rule) -> RuleResult:
    """Send a single rule to Gemini for AI-based contextual validation."""
    prompt = f"""You are a financial document validator for Saudi Arabian financial statements.

RULE: {rule.name}
DESCRIPTION: {rule.description}

TASK: {rule.ai_prompt}

IMPORTANT: Respond in this exact JSON format:
{{"result": "PASS" or "FAIL", "evidence": "what you found (be specific — quote exact text, names, numbers)", "details": "explanation of your finding", "pages": [list of 1-indexed page numbers where evidence was found, e.g. [1, 3, 5]], "evidence_quotes": ["short verbatim text from the PDF (2-8 words each)", "another exact quote"]}}

RULES FOR evidence_quotes:
- Each quote must be an EXACT substring copied verbatim from the PDF text (2-8 words)
- Include 1-3 quotes that pinpoint the key evidence for your judgment
- Quotes must appear on the pages listed in "pages"

Only return the JSON, nothing else."""

    try:
        document_text = doc_data.get("full_text", "")
        response = _call_llm_with_retry(prompt, document_text, pdf_bytes, rule.id)
        data = _parse_llm_json(response)
        return _build_rule_result(rule, data)
    except json.JSONDecodeError:
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


def _check_batch_with_llm(
    pdf_bytes: bytes, doc_data: dict, rules: list[Rule]
) -> dict[str, RuleResult]:
    """Send a batch of rules to Gemini in a single call.

    Falls back to individual calls if the batch response can't be parsed.
    Retries individually for any rules missing from the batch response.
    """
    batch_ids = [r.id for r in rules]

    # Single rule — skip batching overhead
    if len(rules) == 1:
        result = _check_with_llm(pdf_bytes, doc_data, rules[0])
        return {rules[0].id: result}

    # Build combined prompt
    rules_section = ""
    for rule in rules:
        rules_section += f"""
=== RULE {rule.id}: {rule.name} ===
DESCRIPTION: {rule.description}
TASK: {rule.ai_prompt}

"""

    response_template = ",\n  ".join(
        f'"{r.id}": {{"result": "PASS or FAIL", "evidence": "specific evidence", "details": "explanation", "pages": [page_numbers], "evidence_quotes": ["exact quote 1", "exact quote 2"]}}'
        for r in rules
    )

    prompt = f"""You are a financial document validator for Saudi Arabian financial statements.
You must evaluate ALL {len(rules)} rules below against this document. Evaluate each rule INDEPENDENTLY and thoroughly.

{rules_section}
IMPORTANT: Respond with a single JSON object containing ALL {len(rules)} rule IDs as keys:
{{
  {response_template}
}}

RULES FOR evidence_quotes in EVERY rule result:
- Each quote must be an EXACT substring copied verbatim from the PDF text (2-8 words)
- Include 1-3 quotes per rule that pinpoint the key evidence
- Quotes must appear on the pages listed in that rule's "pages" array

Only return the JSON object, nothing else."""

    try:
        document_text = doc_data.get("full_text", "")
        t0 = time.time()
        response = _call_llm_with_retry(prompt, document_text, pdf_bytes, f"batch({','.join(batch_ids)})")
        elapsed = time.time() - t0
        logger.info(f"Batch {batch_ids} completed in {elapsed:.1f}s")

        data = _parse_llm_json(response)

        results: dict[str, RuleResult] = {}
        for rule in rules:
            if rule.id in data and isinstance(data[rule.id], dict):
                results[rule.id] = _build_rule_result(rule, data[rule.id])

        # Retry any rules missing from batch response individually
        missing = [r for r in rules if r.id not in results]
        if missing:
            logger.warning(
                f"{len(missing)} rules missing from batch response: "
                f"{[r.id for r in missing]}, retrying individually"
            )
            for rule in missing:
                try:
                    results[rule.id] = _check_with_llm(pdf_bytes, doc_data, rule)
                except Exception as e:
                    results[rule.id] = RuleResult(
                        rule_id=rule.id, rule_name=rule.name,
                        description=rule.description,
                        status="error",
                        details=f"AI validation failed: {str(e)}",
                        severity=rule.severity.value,
                    )

        return results

    except json.JSONDecodeError:
        logger.warning(f"Batch {batch_ids} JSON parse failed, falling back to individual calls")
        return _fallback_individual(pdf_bytes, doc_data, rules)
    except Exception as e:
        logger.warning(f"Batch {batch_ids} failed ({e}), falling back to individual calls")
        return _fallback_individual(pdf_bytes, doc_data, rules)


def _fallback_individual(
    pdf_bytes: bytes, doc_data: dict, rules: list[Rule]
) -> dict[str, RuleResult]:
    """Run each rule individually as a fallback when batching fails."""
    results: dict[str, RuleResult] = {}
    with ThreadPoolExecutor(max_workers=len(rules)) as executor:
        futures = {
            executor.submit(_check_with_llm, pdf_bytes, doc_data, rule): rule
            for rule in rules
        }
        for future in as_completed(futures):
            rule = futures[future]
            try:
                results[rule.id] = future.result()
            except Exception as e:
                results[rule.id] = RuleResult(
                    rule_id=rule.id, rule_name=rule.name,
                    description=rule.description,
                    status="error",
                    details=f"AI validation failed: {str(e)}",
                    severity=rule.severity.value,
                )
    return results


def run_rules(
    pdf_bytes: bytes,
    doc_data: dict,
    sector: str,
    metadata: Optional[dict] = None,
) -> list[dict]:
    from app.rules.registry import get_rules, RULES

    t_start = time.time()
    applicable_rules = get_rules(sector)
    applicable_ids = {r.id for r in applicable_rules}

    # Mark non-applicable rules (sector mismatch)
    results_map: dict[str, RuleResult] = {}
    for rule in RULES:
        if rule.id not in applicable_ids:
            sector_label = rule.sector.value.replace("_", " ").title()
            results_map[rule.id] = RuleResult(
                rule_id=rule.id, rule_name=rule.name, description=rule.description,
                status="not_applicable",
                details=f"This rule applies only to '{sector_label}' sector. Current sector: '{sector}'.",
                severity=rule.severity.value,
            )

    # Collect rules that need processing
    llm_tasks: list[Rule] = []

    for rule in applicable_rules:
        # Conditional rules without ai_prompt — skip
        if rule.validation_type == ValidationType.CONDITIONAL and not rule.ai_prompt:
            results_map[rule.id] = RuleResult(
                rule_id=rule.id, rule_name=rule.name, description=rule.description,
                status="skip", details="Requires initial form data for comparison",
                severity=rule.severity.value,
            )
            continue

        # R19: Inject metadata into prompt if available
        if rule.id == "R19" and rule.ai_prompt and metadata:
            meta_fields = {k: v for k, v in metadata.items() if v}
            if meta_fields:
                meta_str = "\n".join(f"- {k}: {v}" for k, v in meta_fields.items())
                rule = copy.copy(rule)
                rule.ai_prompt += (
                    f"\n\nADDITIONAL CHECK — FORM DATA SUBMITTED BY USER:\n{meta_str}\n\n"
                    "Compare these submitted values against what you find in the PDF. "
                    "Report any mismatches between the form data and the document content."
                )

        # All rules with ai_prompt go through AI validation
        if rule.ai_prompt:
            llm_tasks.append(rule)
        else:
            results_map[rule.id] = RuleResult(
                rule_id=rule.id, rule_name=rule.name, description=rule.description,
                status="skip", details="No AI prompt configured",
                severity=rule.severity.value,
            )

    # Run AI rules in batched parallel calls
    if llm_tasks:
        batches = [
            llm_tasks[i : i + BATCH_SIZE]
            for i in range(0, len(llm_tasks), BATCH_SIZE)
        ]
        logger.info(
            f"Running {len(llm_tasks)} AI rules in {len(batches)} batch(es) "
            f"(batch_size={BATCH_SIZE}): {[r.id for r in llm_tasks]}"
        )

        t_llm = time.time()
        with ThreadPoolExecutor(max_workers=min(len(batches), MAX_LLM_WORKERS)) as executor:
            futures = {
                executor.submit(_check_batch_with_llm, pdf_bytes, doc_data, batch): batch
                for batch in batches
            }
            for future in as_completed(futures):
                batch = futures[future]
                batch_ids = [r.id for r in batch]
                try:
                    batch_results = future.result()
                    results_map.update(batch_results)
                except Exception as e:
                    logger.error(f"Batch {batch_ids} failed completely: {e}")
                    for rule in batch:
                        results_map[rule.id] = RuleResult(
                            rule_id=rule.id, rule_name=rule.name,
                            description=rule.description,
                            status="error",
                            details=f"AI validation failed: {str(e)}",
                            severity=rule.severity.value,
                        )

        llm_elapsed = time.time() - t_llm
        logger.info(f"All AI rules completed in {llm_elapsed:.1f}s")

    # Resolve evidence quotes to bounding box coordinates using PyMuPDF
    t_coords = time.time()
    for rule_id, result in results_map.items():
        if result.locations:
            resolved = resolve_evidence_locations(pdf_bytes, result.locations)
            result.locations = resolved
    # Strip temporary evidence_quotes from locations
    for rule_id, result in results_map.items():
        for loc in result.locations:
            loc.pop("evidence_quotes", None)
    coords_elapsed = time.time() - t_coords
    logger.info(f"Coordinate resolution completed in {coords_elapsed:.1f}s")

    total_elapsed = time.time() - t_start
    logger.info(f"Rules engine total: {total_elapsed:.1f}s")

    # Return ALL rules in original order (R01-R23)
    ordered_results = []
    for rule in RULES:
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
            "pages": [loc["page"] for loc in r.locations if loc.get("page")],
            "locations": r.locations,
        }
        for r in ordered_results
    ]
