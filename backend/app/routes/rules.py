from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from dataclasses import asdict

from app.rules.registry import (
    Rule, Category, Sector, Severity, ValidationType,
    get_rules, get_rule, add_rule, update_rule, delete_rule,
)

router = APIRouter(prefix="/api/rules", tags=["rules"])


class RuleCreate(BaseModel):
    id: str
    name: str
    name_ar: str
    description: str
    category: str
    sector: str
    severity: str
    validation_type: str
    keywords: list[str] = []
    ai_prompt: Optional[str] = None


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    sector: Optional[str] = None
    severity: Optional[str] = None
    validation_type: Optional[str] = None
    keywords: Optional[list[str]] = None
    ai_prompt: Optional[str] = None


@router.get("")
def list_rules(sector: Optional[str] = Query(None, description="Filter by sector: all, banking_insurance, npo")):
    rules = get_rules(sector)
    return {"count": len(rules), "rules": [asdict(r) for r in rules]}


@router.get("/{rule_id}")
def get_rule_by_id(rule_id: str):
    rule = get_rule(rule_id.upper())
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return asdict(rule)


@router.post("", status_code=201)
def create_rule(body: RuleCreate):
    try:
        rule = Rule(
            id=body.id.upper(),
            name=body.name,
            name_ar=body.name_ar,
            description=body.description,
            category=Category(body.category),
            sector=Sector(body.sector),
            severity=Severity(body.severity),
            validation_type=ValidationType(body.validation_type),
            keywords=body.keywords,
            ai_prompt=body.ai_prompt,
        )
        add_rule(rule)
        return asdict(rule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{rule_id}")
def update_rule_by_id(rule_id: str, body: RuleUpdate):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    rule = update_rule(rule_id.upper(), updates)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return asdict(rule)


@router.delete("/{rule_id}")
def delete_rule_by_id(rule_id: str):
    if not delete_rule(rule_id.upper()):
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return {"message": f"Rule {rule_id.upper()} deleted"}
