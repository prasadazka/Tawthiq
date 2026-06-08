"""Saudi-IFRS XBRL generation endpoint.

Frontend posts the already-extracted rules_json + tables_json + metadata
(no PDF re-upload). Server runs source_mapper → ai_fallback → xbrl_generator
and returns the XBRL XML document.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.xbrl.saudi.ai_fallback import run_ai_fallback
from app.xbrl.saudi.source_mapper import map_concepts
from app.xbrl.saudi.taxonomy_loader import default_taxonomy
from app.xbrl.saudi.xbrl_generator import generate_xbrl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/xbrl/saudi", tags=["xbrl-saudi"])


class GenerateRequest(BaseModel):
    rules_json: dict = Field(..., description="Response from /api/validate")
    tables_json: dict = Field(..., description="Response from /api/pdf-tables/extract")
    metadata: dict = Field(default_factory=dict, description="Entity + period + currency")
    use_ai_fallback: bool = Field(True, description="Run the second-pass AI mapping")
    filename: str = Field("saudi_xbrl.xml")


@router.post("/generate")
async def generate(req: GenerateRequest):
    """Return the XBRL instance document as an XML attachment."""
    t_total = time.time()
    try:
        tax = default_taxonomy()
        facts = map_concepts(req.rules_json, req.tables_json, tax)
        t_after_map = time.time()
        direct_found = len(facts.found())

        if req.use_ai_fallback:
            facts = run_ai_fallback(facts, req.tables_json, tax)
        t_after_ai = time.time()
        total_found = len(facts.found())
        data_total = len(facts.facts) - len(facts.artifacts())

        xml = generate_xbrl(facts, req.metadata, tax)
    except Exception as exc:
        logger.exception("Saudi XBRL generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}")

    elapsed = round(time.time() - t_total, 1)
    headers = {
        "Content-Disposition": f'attachment; filename="{req.filename}"',
        "X-Tawthiq-Concepts-Total": str(data_total),
        "X-Tawthiq-Concepts-Direct": str(direct_found),
        "X-Tawthiq-Concepts-Found": str(total_found),
        "X-Tawthiq-Coverage-Pct": f"{facts.coverage_pct}",
        "X-Tawthiq-Elapsed-Seconds": f"{elapsed}",
        "X-Tawthiq-Map-Seconds": f"{round(t_after_map - t_total, 2)}",
        "X-Tawthiq-AI-Seconds": f"{round(t_after_ai - t_after_map, 1)}",
        "Access-Control-Expose-Headers": (
            "X-Tawthiq-Concepts-Total,X-Tawthiq-Concepts-Direct,"
            "X-Tawthiq-Concepts-Found,X-Tawthiq-Coverage-Pct,"
            "X-Tawthiq-Elapsed-Seconds,X-Tawthiq-Map-Seconds,X-Tawthiq-AI-Seconds"
        ),
    }
    return Response(content=xml, media_type="application/xml", headers=headers)


@router.post("/preview")
async def preview(req: GenerateRequest):
    """Same pipeline, but returns JSON with per-concept resolution detail
    instead of XML. Useful for the UI's preview pane."""
    try:
        tax = default_taxonomy()
        facts = map_concepts(req.rules_json, req.tables_json, tax)
        if req.use_ai_fallback:
            facts = run_ai_fallback(facts, req.tables_json, tax)
    except Exception as exc:
        logger.exception("Saudi XBRL preview failed")
        raise HTTPException(status_code=500, detail=f"Preview failed: {exc}")

    return {
        "coverage_pct": facts.coverage_pct,
        "summary": {
            "total": len(facts.facts),
            "found": len(facts.found()),
            "missing": len(facts.missing()),
            "artifacts": len(facts.artifacts()),
        },
        "facts": [
            {
                "business_term": f.business_term,
                "xbrl_tag": f.xbrl_tag,
                "section_id": f.section_id,
                "status": f.status,
                "source": f.source,
                "value_cy": f.value_cy,
                "value_py": f.value_py,
                "currency": f.currency,
                "page": f.page,
                "evidence": f.evidence,
                "matched_via": f.matched_via,
                "reason": f.reason,
            }
            for f in facts.facts
        ],
    }
