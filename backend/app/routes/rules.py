from fastapi import APIRouter, Query
from typing import Optional
from dataclasses import asdict

from app.rules.registry import get_rules

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("")
def list_rules(sector: Optional[str] = Query(None, description="Filter by sector: all, banking_insurance, npo")):
    rules = get_rules(sector)
    return {"count": len(rules), "rules": [asdict(r) for r in rules]}
