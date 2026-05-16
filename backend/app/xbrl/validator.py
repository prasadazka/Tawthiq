"""Generic XBRL pre-generation validator.

Loads a country-specific validation_rules.yml and runs each rule against
extracted JSON data. Returns a structured report.

Adding a country = new validation_rules.yml. No code change needed unless
a new check_type is required.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass
class RuleResult:
    rule_id: str
    name: str
    category: str
    severity: str
    status: str            # "pass" | "fail" | "skip"
    message: str = ""
    actual: Any = None
    expected: Any = None


@dataclass
class ValidationReport:
    passed: bool                       # True if no error-severity rule failed
    rules: list[RuleResult] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def blocking_failures(self) -> list[RuleResult]:
        return [r for r in self.rules if r.severity == "error" and r.status == "fail"]

    @property
    def warnings(self) -> list[RuleResult]:
        return [r for r in self.rules if r.severity == "warning" and r.status == "fail"]


def _get(data: dict, path: str) -> Any:
    """Traverse dotted path. Returns None if any segment missing."""
    if not path:
        return None
    cur = data
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _months_between(d1: date, d2: date) -> int:
    return (d2.year - d1.year) * 12 + (d2.month - d1.month) + (1 if d2.day >= d1.day else 0)


class IndianXBRLValidator:
    """Loads validation_rules.yml and runs every rule against extracted JSON."""

    def __init__(self, rules_path: str | Path):
        with open(rules_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.rules = self.config.get("rules", [])
        self.behavior = self.config.get("behavior", {})

    # ── public API ────────────────────────────────────────────────────────────

    def validate(self, data: dict) -> ValidationReport:
        results: list[RuleResult] = []
        for rule in self.rules:
            results.append(self._run_rule(rule, data))

        summary = {"pass": 0, "fail": 0, "skip": 0}
        for r in results:
            summary[r.status] = summary.get(r.status, 0) + 1

        block_severity = self.behavior.get("block_on_severity", "error")
        passed = not any(
            r.severity == block_severity and r.status == "fail" for r in results
        )
        return ValidationReport(passed=passed, rules=results, summary=summary)

    # ── rule dispatcher ───────────────────────────────────────────────────────

    def _run_rule(self, rule: dict, data: dict) -> RuleResult:
        ct = rule.get("check_type")
        params = rule.get("check_params", {})
        handler = getattr(self, f"_check_{ct}", None)

        base = dict(
            rule_id=rule["id"],
            name=rule["name"],
            category=rule.get("category", ""),
            severity=rule.get("severity", "error"),
        )

        if handler is None:
            return RuleResult(
                **base, status="skip", message=f"Unknown check_type '{ct}'"
            )

        try:
            return handler(rule, params, data, base)
        except Exception as exc:
            return RuleResult(
                **base, status="fail", message=f"Validator error: {exc}"
            )

    # ── individual check_type implementations ─────────────────────────────────

    def _check_required(self, rule, p, data, base) -> RuleResult:
        v = _get(data, p["field"])
        if v is None or v == "":
            return RuleResult(**base, status="fail", message=rule.get("error_message") or f"{p['field']} is missing", actual=v)
        return RuleResult(**base, status="pass", actual=v)

    def _check_regex(self, rule, p, data, base) -> RuleResult:
        v = _get(data, p["field"])
        required = p.get("required", False)
        if v is None:
            if required:
                return RuleResult(**base, status="fail", message=rule.get("error_message") or f"{p['field']} is required")
            return RuleResult(**base, status="pass", message="Optional field absent")
        if not isinstance(v, str) or not re.match(p["pattern"], v):
            return RuleResult(**base, status="fail", message=rule.get("error_message") or f"{p['field']} does not match pattern {p['pattern']}", actual=v)
        return RuleResult(**base, status="pass", actual=v)

    def _check_string_length(self, rule, p, data, base) -> RuleResult:
        v = _get(data, p["field"])
        required = p.get("required", False)
        if v is None:
            if required:
                return RuleResult(**base, status="fail", message=f"{p['field']} is required")
            return RuleResult(**base, status="pass", message="Optional field absent")
        if not isinstance(v, str):
            return RuleResult(**base, status="fail", message=f"{p['field']} not a string", actual=type(v).__name__)
        n = len(v)
        if "min" in p and n < p["min"]:
            return RuleResult(**base, status="fail", message=f"{p['field']} too short ({n} < {p['min']})", actual=n)
        if "max" in p and n > p["max"]:
            return RuleResult(**base, status="fail", message=f"{p['field']} too long ({n} > {p['max']})", actual=n)
        return RuleResult(**base, status="pass", actual=n)

    def _check_number_range(self, rule, p, data, base) -> RuleResult:
        v = _get(data, p["field"])
        required = p.get("required", False)
        if v is None:
            if required:
                return RuleResult(**base, status="fail", message=f"{p['field']} is required")
            return RuleResult(**base, status="pass", message="Optional field absent")
        if not isinstance(v, (int, float)):
            return RuleResult(**base, status="fail", message=f"{p['field']} not numeric", actual=type(v).__name__)
        if "min" in p:
            if p.get("exclusive_min") and v <= p["min"]:
                return RuleResult(**base, status="fail", message=f"{p['field']} must be > {p['min']}", actual=v)
            if not p.get("exclusive_min") and v < p["min"]:
                return RuleResult(**base, status="fail", message=f"{p['field']} must be >= {p['min']}", actual=v)
        if "max" in p and v > p["max"]:
            return RuleResult(**base, status="fail", message=f"{p['field']} must be <= {p['max']}", actual=v)
        return RuleResult(**base, status="pass", actual=v)

    def _check_enum(self, rule, p, data, base) -> RuleResult:
        v = _get(data, p["field"])
        required = p.get("required", False)
        if v is None:
            if required:
                return RuleResult(**base, status="fail", message=f"{p['field']} is required")
            return RuleResult(**base, status="pass", message="Optional field absent")
        allowed = p.get("allowed", [])
        if v not in allowed:
            return RuleResult(**base, status="fail", message=f"{v!r} not in allowed values {allowed}", actual=v, expected=allowed)
        return RuleResult(**base, status="pass", actual=v)

    def _check_all_required(self, rule, p, data, base) -> RuleResult:
        missing = [f for f in p["fields"] if _get(data, f) in (None, "")]
        if missing:
            return RuleResult(**base, status="fail", message=f"Missing fields: {', '.join(missing)}", actual=missing)
        return RuleResult(**base, status="pass")

    def _check_array_min_length(self, rule, p, data, base) -> RuleResult:
        v = _get(data, p["field"]) or []
        if not isinstance(v, list):
            return RuleResult(**base, status="fail", message=f"{p['field']} not an array", actual=type(v).__name__)
        if len(v) < p["min"]:
            return RuleResult(**base, status="fail", message=f"{p['field']} has {len(v)} items (need >= {p['min']})", actual=len(v))
        return RuleResult(**base, status="pass", actual=len(v))

    def _check_array_all_match(self, rule, p, data, base) -> RuleResult:
        items = _get(data, p["field"]) or []
        sub = p["sub_check"]
        failures = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                failures.append({"index": idx, "reason": "item not an object"})
                continue
            sub_result = self._run_sub_check(sub, item)
            if sub_result.status == "fail":
                failures.append({"index": idx, "reason": sub_result.message})
        if failures:
            return RuleResult(**base, status="fail", message=f"{len(failures)} item(s) failed sub-check", actual=failures)
        return RuleResult(**base, status="pass", actual=len(items))

    def _check_array_any_match(self, rule, p, data, base) -> RuleResult:
        items = _get(data, p["field"]) or []
        sub = p["sub_check"]
        for item in items:
            if not isinstance(item, dict):
                continue
            sub_result = self._run_sub_check(sub, item)
            if sub_result.status == "pass":
                return RuleResult(**base, status="pass")
        return RuleResult(**base, status="fail", message=rule.get("error_message") or "No array item satisfies the sub-check")

    def _check_array_sum_max(self, rule, p, data, base) -> RuleResult:
        items = _get(data, p["field"]) or []
        total = 0.0
        for it in items:
            v = it.get(p["sum_of"]) if isinstance(it, dict) else None
            if isinstance(v, (int, float)):
                total += v
        if total > p["max"] + p.get("tolerance", 0):
            return RuleResult(**base, status="fail", message=f"Sum {total} > max {p['max']}", actual=total)
        return RuleResult(**base, status="pass", actual=total)

    def _check_fields_equal(self, rule, p, data, base) -> RuleResult:
        a = _get(data, p["field_a"])
        b = self._resolve_value_or_expr(p, "field_b", data)
        if a is None or b is None:
            return RuleResult(**base, status="fail", message=f"One side is null (a={a}, b={b})")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return RuleResult(**base, status="fail", message="Non-numeric operands", actual={"a": a, "b": b})
        tol = p.get("tolerance", 0)
        if abs(a - b) > tol:
            return RuleResult(**base, status="fail", message=f"|{a} - {b}| = {abs(a - b)} > tolerance {tol}", actual={"a": a, "b": b, "diff": a - b})
        return RuleResult(**base, status="pass", actual={"a": a, "b": b})

    def _check_fields_sum(self, rule, p, data, base) -> RuleResult:
        total = _get(data, p["total_field"])
        if total is None:
            return RuleResult(**base, status="fail", message=f"{p['total_field']} is missing")
        parts = [_get(data, f) or 0 for f in p["sum_fields"]]
        s = sum(parts)
        tol = p.get("tolerance", 0)
        if abs(total - s) > tol:
            return RuleResult(**base, status="fail", message=f"Total {total} != sum {s} (tol {tol})", actual={"total": total, "sum": s, "parts": parts})
        return RuleResult(**base, status="pass", actual={"total": total, "sum": s})

    def _check_date_after(self, rule, p, data, base) -> RuleResult:
        d1 = _parse_date(_get(data, p["field"]))
        d2 = _parse_date(_get(data, p["after_field"]))
        if d1 is None or d2 is None:
            return RuleResult(**base, status="fail", message=f"Date parse failed (field={d1}, after={d2})")
        if not (d1 > d2):
            return RuleResult(**base, status="fail", message=f"{p['field']} ({d1}) is not after {p['after_field']} ({d2})", actual={"field": str(d1), "after": str(d2)})
        return RuleResult(**base, status="pass", actual={"field": str(d1), "after": str(d2)})

    def _check_date_diff_months(self, rule, p, data, base) -> RuleResult:
        d1 = _parse_date(_get(data, p["from_field"]))
        d2 = _parse_date(_get(data, p["to_field"]))
        if d1 is None or d2 is None:
            return RuleResult(**base, status="fail", message="Date parse failed")
        diff = _months_between(d1, d2)
        expected = p["expected"]
        tol = p.get("tolerance_months", 0)
        if abs(diff - expected) > tol:
            return RuleResult(**base, status="fail", message=f"Period is {diff} months, expected {expected}", actual=diff)
        return RuleResult(**base, status="pass", actual=diff)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _resolve_value_or_expr(self, params: dict, key: str, data: dict) -> Any:
        """Resolve a value that may be either a field path or an expression."""
        expr_key = key + "_expression"
        if expr_key in params:
            expr = params[expr_key]
            op = expr["operation"]
            operands = [_get(data, f) for f in expr["operands"]]
            if any(o is None for o in operands):
                return None
            if op == "add":
                return sum(operands)
            if op == "subtract":
                result = operands[0]
                for o in operands[1:]:
                    result -= o
                return result
            if op == "multiply":
                result = 1
                for o in operands:
                    result *= o
                return result
            raise ValueError(f"Unknown operation: {op}")
        if key in params:
            return _get(data, params[key])
        return None

    def _run_sub_check(self, sub: dict, item: dict) -> RuleResult:
        """Run a sub-check against a single array item using the item as root."""
        fake_rule = {"id": "__sub__", "name": "sub", "category": "", "severity": "error", **sub}
        return self._run_rule(fake_rule, item)
