import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


class Sector(str, Enum):
    ALL = "all"
    BANKING_INSURANCE = "banking_insurance"
    NPO = "npo"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class Category(str, Enum):
    AUDITOR = "auditor"
    FORMAT = "format"
    CONTENT = "content"
    FINANCIAL = "financial"
    SECTOR_SPECIFIC = "sector_specific"


class ValidationType(str, Enum):
    PRESENCE_CHECK = "presence_check"
    PATTERN_MATCH = "pattern_match"
    FIELD_EXTRACTION = "field_extraction"
    AI_JUDGMENT = "ai_judgment"
    CONDITIONAL = "conditional"


@dataclass
class Rule:
    id: str
    name: str
    name_ar: str
    description: str
    category: Category
    sector: Sector
    severity: Severity
    validation_type: ValidationType
    keywords: list[str] = field(default_factory=list)
    ai_prompt: Optional[str] = None


RULES_FILE = Path(__file__).parent / "rules.json"


def _load_rules() -> list[Rule]:
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [
        Rule(
            id=r["id"],
            name=r["name"],
            name_ar=r["name_ar"],
            description=r["description"],
            category=Category(r["category"]),
            sector=Sector(r["sector"]),
            severity=Severity(r["severity"]),
            validation_type=ValidationType(r["validation_type"]),
            keywords=r.get("keywords", []),
            ai_prompt=r.get("ai_prompt"),
        )
        for r in data
    ]


def _save_rules(rules: list[Rule]):
    data = []
    for r in rules:
        d = asdict(r)
        d["category"] = r.category.value
        d["sector"] = r.sector.value
        d["severity"] = r.severity.value
        d["validation_type"] = r.validation_type.value
        data.append(d)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Load rules on startup
RULES: list[Rule] = _load_rules()


def get_rules(sector: str | None = None) -> list[Rule]:
    if sector is None:
        return RULES
    return [r for r in RULES if r.sector == Sector.ALL or r.sector.value == sector]


def get_rule(rule_id: str) -> Rule | None:
    return next((r for r in RULES if r.id == rule_id), None)


def add_rule(rule: Rule) -> Rule:
    if any(r.id == rule.id for r in RULES):
        raise ValueError(f"Rule {rule.id} already exists")
    RULES.append(rule)
    _save_rules(RULES)
    return rule


def update_rule(rule_id: str, updates: dict) -> Rule | None:
    rule = get_rule(rule_id)
    if not rule:
        return None
    for key, value in updates.items():
        if hasattr(rule, key) and key != "id":
            if key == "category":
                value = Category(value)
            elif key == "sector":
                value = Sector(value)
            elif key == "severity":
                value = Severity(value)
            elif key == "validation_type":
                value = ValidationType(value)
            setattr(rule, key, value)
    _save_rules(RULES)
    return rule


def delete_rule(rule_id: str) -> bool:
    rule = get_rule(rule_id)
    if not rule:
        return False
    RULES.remove(rule)
    _save_rules(RULES)
    return True
