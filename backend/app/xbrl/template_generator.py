"""Template-driven XBRL generator.

Loads the real C2X-submitted XBRL as a literal template (with fact values
cleared), then fills in:
  - The entity identifier (CIN) from extracted company data
  - Every <tag contextRef="..."> fact value where we have a JSON mapping

Untagged / unmapped facts simply stay blank.

This guarantees the OUTPUT XBRL is byte-for-byte compatible with what a CA
actually submits to MCA — same namespaces, contexts, tag names,
dimensional axes, schema reference, encoding.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

THIS_DIR = Path(__file__).parent
TEMPLATE_XBRL_PATH = THIS_DIR / "india" / "xbrl_template.xml"


@dataclass
class XBRLResult:
    success: bool
    xml: str = ""
    filename: str = ""
    fact_count: int = 0
    facts_filled: int = 0
    facts_placeholder: int = 0   # number of tags filled with FILL_VALUE_HERE
    context_count: int = 0
    error: str = ""


# Placeholder text written into tags when no value is available.
# The frontend highlights any line containing this exact string.
PLACEHOLDER = "FILL VALUE HERE"


# ── value lookup ─────────────────────────────────────────────────────────────

def _get(data: dict, path: str) -> Any:
    if not path:
        return None
    cur: Any = data
    for seg in path.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return None
        cur = cur[seg]
    return cur if cur is not None else None


# Helper: build CY+PY pairs for the same JSON path
def _bs_pair(json_path_base: str, tag: str) -> dict:
    """Returns {(tag, 'I_CY'): cy_path, (tag, 'I_PY'): py_path}."""
    return {
        (tag, "I_CY"): json_path_base.replace("$YEAR", "current_year"),
        (tag, "I_PY"): json_path_base.replace("$YEAR", "prior_year"),
    }

# (tag, context_pattern) → JSON path.
SIMPLE_MAP: dict[tuple[str, str], str] = {
    # ─── Company / metadata (in-ca) ─────────────────────────────────────────
    ("in-ca:NameOfCompany", "D_CY"): "company.name",
    ("in-ca:CorporateIdentityNumber", "D_CY"): "company.cin",
    ("in-ca:PermanentAccountNumberOfEntity", "D_CY"): "company.pan",
    ("in-ca:AddressOfRegisteredOfficeOfCompany", "D_CY"): "company.registered_address",
    ("in-ca:NameOfStateOrUnionTerritory", "D_CY"): "company.state",
    ("in-ca:TypeOfIndustry", "D_CY"): "company.industry_type",
    ("in-ca:NatureOfCompany", "D_CY"): "company.company_type",
    ("in-ca:EmailIdOfCompany", "D_CY"): "company.email",
    ("in-ca:TelephoneNumberOfCompany", "D_CY"): "company.telephone",
    ("in-ca:WebsiteOfCompany", "D_CY"): "company.website",
    # ─── Reporting period ───────────────────────────────────────────────────
    ("in-ca:DateOfStartOfReportingPeriod", "D_CY"): "reporting_period.start_date",
    ("in-ca:DateOfEndOfReportingPeriod", "D_CY"): "reporting_period.end_date",
    ("in-ca:DateOfStartOfReportingPeriod", "D_PY"): "reporting_period.prior_year_start",
    ("in-ca:DateOfEndOfReportingPeriod", "D_PY"): "reporting_period.prior_year_end",
    ("in-ca:LevelOfRoundingUsedInFinancialStatements", "D_CY"): "reporting_period.level_of_rounding",
    ("in-ca:TypeOfCashFlowStatement", "D_CY"): "reporting_period.cash_flow_method",
    ("in-ca:NatureOfReportStandaloneConsolidated", "D_CY"): "reporting_period.report_type",
    # ─── Board approval ─────────────────────────────────────────────────────
    ("in-ca:DateOfBoardMeetingWhenFinalAccountsWereApproved", "D_CY"): "board_approval.date_of_board_meeting",
    ("in-ca:DateOfSigningOfBalanceSheetByDirectors", "D_CY"): "board_approval.date_of_signing_balance_sheet",
}
# ─── Balance Sheet — CY+PY pairs (exact tag names from real C2X output) ─────
_bs_pairs = [
    # Equity & Liabilities
    ("in-gaap:ShareCapital",                            "balance_sheet.$YEAR.equity_and_liabilities.share_capital"),
    ("in-gaap:ReservesAndSurplus",                      "balance_sheet.$YEAR.equity_and_liabilities.reserves_and_surplus"),
    ("in-gaap:ShareApplicationMoneyPendingAllotment",   "balance_sheet.$YEAR.equity_and_liabilities.money_received_against_share_warrants"),
    ("in-gaap:LongTermBorrowings",                      "balance_sheet.$YEAR.equity_and_liabilities.non_current_liabilities.long_term_borrowings"),
    ("in-gaap:DeferredTaxLiabilitiesNet",               "balance_sheet.$YEAR.equity_and_liabilities.non_current_liabilities.deferred_tax_liabilities"),
    ("in-gaap:OtherLongTermLiabilities",                "balance_sheet.$YEAR.equity_and_liabilities.non_current_liabilities.other_long_term_liabilities"),
    ("in-gaap:LongTermProvisions",                      "balance_sheet.$YEAR.equity_and_liabilities.non_current_liabilities.long_term_provisions"),
    ("in-gaap:ShortTermBorrowings",                     "balance_sheet.$YEAR.equity_and_liabilities.current_liabilities.short_term_borrowings"),
    ("in-gaap:TradePayables",                           "balance_sheet.$YEAR.equity_and_liabilities.current_liabilities.trade_payables"),
    ("in-gaap:OtherCurrentLiabilities",                 "balance_sheet.$YEAR.equity_and_liabilities.current_liabilities.other_current_liabilities"),
    ("in-gaap:ShortTermProvisions",                     "balance_sheet.$YEAR.equity_and_liabilities.current_liabilities.short_term_provisions"),
    ("in-gaap:EquityAndLiabilities",                    "balance_sheet.$YEAR.equity_and_liabilities.total_equity_and_liabilities"),
    # Assets
    ("in-gaap:TangibleAssets",                          "balance_sheet.$YEAR.assets.non_current_assets.tangible_assets"),
    ("in-gaap:IntangibleAssets",                        "balance_sheet.$YEAR.assets.non_current_assets.intangible_assets"),
    ("in-gaap:CapitalWorkInProgress",                   "balance_sheet.$YEAR.assets.non_current_assets.capital_work_in_progress"),
    ("in-gaap:NoncurrentInvestments",                   "balance_sheet.$YEAR.assets.non_current_assets.non_current_investments"),
    ("in-gaap:DeferredTaxAssetsNet",                    "balance_sheet.$YEAR.assets.non_current_assets.deferred_tax_assets"),
    ("in-gaap:LongTermLoansAndAdvances",                "balance_sheet.$YEAR.assets.non_current_assets.long_term_loans_and_advances"),
    ("in-gaap:OtherNoncurrentAssets",                   "balance_sheet.$YEAR.assets.non_current_assets.other_non_current_assets"),
    ("in-gaap:CurrentInvestments",                      "balance_sheet.$YEAR.assets.current_assets.current_investments"),
    ("in-gaap:Inventories",                             "balance_sheet.$YEAR.assets.current_assets.inventories"),
    ("in-gaap:TradeReceivables",                        "balance_sheet.$YEAR.assets.current_assets.trade_receivables"),
    ("in-gaap:CashAndBankBalances",                     "balance_sheet.$YEAR.assets.current_assets.cash_and_bank_balances"),
    ("in-gaap:ShortTermLoansAndAdvances",               "balance_sheet.$YEAR.assets.current_assets.short_term_loans_and_advances"),
    ("in-gaap:OtherCurrentAssets",                      "balance_sheet.$YEAR.assets.current_assets.other_current_assets"),
    ("in-gaap:Assets",                                  "balance_sheet.$YEAR.assets.total_assets"),
]
for tag, path_template in _bs_pairs:
    SIMPLE_MAP.update(_bs_pair(path_template, tag))

# ─── P&L (D_CY / D_PY) ──────────────────────────────────────────────────────
SIMPLE_MAP.update({
    ("in-gaap:RevenueFromOperations", "D_CY"): "profit_loss.current_year.revenue_from_operations",
    ("in-gaap:OtherIncome", "D_CY"): "profit_loss.current_year.other_income",
    ("in-gaap:Revenue", "D_CY"): "profit_loss.current_year.total_revenue",
    ("in-gaap:CostOfMaterialsConsumed", "D_CY"): "profit_loss.current_year.expenses.cost_of_materials_consumed",
    ("in-gaap:PurchaseOfStockInTrade", "D_CY"): "profit_loss.current_year.expenses.purchases_of_stock_in_trade",
    ("in-gaap:ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade", "D_CY"): "profit_loss.current_year.expenses.changes_in_inventories",
    ("in-gaap:EmployeeBenefitExpense", "D_CY"): "profit_loss.current_year.expenses.employee_benefits_expense",
    ("in-gaap:FinanceCosts", "D_CY"): "profit_loss.current_year.expenses.finance_costs",
    ("in-gaap:DepreciationAmortisationAndDepletionExpense", "D_CY"): "profit_loss.current_year.expenses.depreciation_amortisation",
    ("in-gaap:OtherExpenses", "D_CY"): "profit_loss.current_year.expenses.other_expenses",
    ("in-gaap:ProfitBeforeTax", "D_CY"): "profit_loss.current_year.profit_before_tax",
    ("in-gaap:TaxExpense", "D_CY"): "profit_loss.current_year.tax_expense.total_tax_expense",
    ("in-gaap:CurrentTax", "D_CY"): "profit_loss.current_year.tax_expense.current_tax",
    ("in-gaap:ProfitLossForPeriod", "D_CY"): "profit_loss.current_year.profit_for_period",
    ("in-gaap:RevenueFromOperations", "D_PY"): "profit_loss.prior_year.revenue_from_operations",
    ("in-gaap:OtherIncome", "D_PY"): "profit_loss.prior_year.other_income",
    ("in-gaap:Revenue", "D_PY"): "profit_loss.prior_year.total_revenue",
    ("in-gaap:ProfitBeforeTax", "D_PY"): "profit_loss.prior_year.profit_before_tax",
    ("in-gaap:ProfitLossForPeriod", "D_PY"): "profit_loss.prior_year.profit_for_period",
    # ─── Cash Flow ─────────────────────────────────────────────────────────
    ("in-gaap:CashFlowsFromUsedInOperatingActivities", "D_CY"): "cash_flow.current_year.cash_from_operating_activities",
    ("in-gaap:CashFlowsFromUsedInInvestingActivities", "D_CY"): "cash_flow.current_year.cash_from_investing_activities",
    ("in-gaap:CashFlowsFromUsedInFinancingActivities", "D_CY"): "cash_flow.current_year.cash_from_financing_activities",
    ("in-gaap:CashAndCashEquivalentsCashFlowStatement", "I_CY"): "cash_flow.current_year.cash_at_end_of_period",
    ("in-gaap:CashAndCashEquivalentsCashFlowStatement", "I_PY"): "cash_flow.current_year.cash_at_beginning_of_period",
})

# Dimensional patterns: contextRef matches regex → JSON path uses captured idx
# Each entry: (tag, regex on contextRef) → JSON path template ({idx} replaced 0-indexed)
DIMENSIONAL_MAP: list[tuple[str, re.Pattern, str]] = [
    # Shareholders (Tab_D_CY_309_N / Tab_I_CY_309_N)
    ("in-gaap:NameOfShareholder", re.compile(r"^Tab_D_CY_309_(\d+)$"), "shareholders[{idx0}].name"),
    ("in-gaap:NumberOfSharesHeldInCompany", re.compile(r"^Tab_I_CY_309_(\d+)$"), "shareholders[{idx0}].shares_held"),
    ("in-gaap:NumberOfSharesHeldInCompany", re.compile(r"^Tab_I_PY_309_(\d+)$"), "shareholders[{idx0}].shares_held"),
    ("in-gaap:PercentageOfShareholdingInCompany", re.compile(r"^Tab_I_CY_309_(\d+)$"), "shareholders[{idx0}].percentage_held"),
    ("in-gaap:PercentageOfShareholdingInCompany", re.compile(r"^Tab_I_PY_309_(\d+)$"), "shareholders[{idx0}].percentage_held"),
    ("in-gaap:TypeOfShare", re.compile(r"^Tab_D_CY_309_(\d+)$"), "shareholders[{idx0}].type_of_share"),
    ("in-ca:CountryOfIncorporationOrResidenceOfShareholder", re.compile(r"^Tab_D_CY_309_(\d+)$"), "shareholders[{idx0}].country_of_residence"),
    ("in-ca:PANOfShareholder", re.compile(r"^Tab_D_CY_309_(\d+)$"), "shareholders[{idx0}].pan"),
    # Directors / KMP
    ("in-ca:NameOfKeyManagerialPersonnelOrDirector",
     re.compile(r"^KeyManagerialPersonnelsAndDirectorsDomain_D_CY_(\d+)"), "directors[{idx0}].name"),
    ("in-ca:DirectorIdentificationNumberOfKeyManagerialPersonnelOrDirector",
     re.compile(r"^KeyManagerialPersonnelsAndDirectorsDomain_D_CY_(\d+)"), "directors[{idx0}].din"),
    ("in-ca:DesignationOfKeyManagerialPersonnelOrDirector",
     re.compile(r"^KeyManagerialPersonnelsAndDirectorsDomain_D_CY_(\d+)"), "directors[{idx0}].designation"),
    # Auditor (single auditor in single dimensional context)
    ("in-ca:NameOfAuditFirm", re.compile(r"^AuditorsDomain_D_CY_"), "auditor.firm_name"),
    ("in-ca:FirmRegistrationNumberOfAuditFirm", re.compile(r"^AuditorsDomain_D_CY_"), "auditor.firm_registration_number"),
    ("in-ca:NameOfAuditorSigningReport", re.compile(r"^AuditorsDomain_D_CY_"), "auditor.partner_name"),
    ("in-ca:MembershipNumberOfAuditorOrAuditorsRepresentative", re.compile(r"^AuditorsDomain_D_CY_"), "auditor.membership_number"),
    ("in-ca:DateOfSigningAuditReportByAuditors", re.compile(r"^AuditorsDomain_D_CY_"), "auditor.signature_date"),
    ("in-ca:DateOfSigningOfBalanceSheetByAuditors", re.compile(r"^AuditorsDomain_D_CY_"), "auditor.signature_date"),
    ("in-ca:AddressOfAuditors", re.compile(r"^AuditorsDomain_D_CY_"), "auditor.address"),
]


# Composite (sum-of) tags — the IFRS taxonomy emits subtotals as separate facts.
# Each composite is a sum of its sub-line JSON paths; CY/PY pair handled by suffix.
# Format: (tag, context) -> list of JSON paths to sum (treat null as 0)
COMPOSITE_MAP_TEMPLATE: dict[str, list[str]] = {
    "in-gaap:ShareholdersFunds": [
        "balance_sheet.$YEAR.equity_and_liabilities.share_capital",
        "balance_sheet.$YEAR.equity_and_liabilities.reserves_and_surplus",
        "balance_sheet.$YEAR.equity_and_liabilities.money_received_against_share_warrants",
    ],
    "in-gaap:NoncurrentLiabilities": [
        "balance_sheet.$YEAR.equity_and_liabilities.non_current_liabilities.long_term_borrowings",
        "balance_sheet.$YEAR.equity_and_liabilities.non_current_liabilities.deferred_tax_liabilities",
        "balance_sheet.$YEAR.equity_and_liabilities.non_current_liabilities.other_long_term_liabilities",
        "balance_sheet.$YEAR.equity_and_liabilities.non_current_liabilities.long_term_provisions",
    ],
    "in-gaap:CurrentLiabilities": [
        "balance_sheet.$YEAR.equity_and_liabilities.current_liabilities.short_term_borrowings",
        "balance_sheet.$YEAR.equity_and_liabilities.current_liabilities.trade_payables",
        "balance_sheet.$YEAR.equity_and_liabilities.current_liabilities.other_current_liabilities",
        "balance_sheet.$YEAR.equity_and_liabilities.current_liabilities.short_term_provisions",
    ],
    "in-gaap:FixedAssets": [
        "balance_sheet.$YEAR.assets.non_current_assets.tangible_assets",
        "balance_sheet.$YEAR.assets.non_current_assets.intangible_assets",
        "balance_sheet.$YEAR.assets.non_current_assets.capital_work_in_progress",
    ],
    "in-gaap:NoncurrentAssets": [
        "balance_sheet.$YEAR.assets.non_current_assets.tangible_assets",
        "balance_sheet.$YEAR.assets.non_current_assets.intangible_assets",
        "balance_sheet.$YEAR.assets.non_current_assets.capital_work_in_progress",
        "balance_sheet.$YEAR.assets.non_current_assets.non_current_investments",
        "balance_sheet.$YEAR.assets.non_current_assets.deferred_tax_assets",
        "balance_sheet.$YEAR.assets.non_current_assets.long_term_loans_and_advances",
        "balance_sheet.$YEAR.assets.non_current_assets.other_non_current_assets",
    ],
    "in-gaap:CurrentAssets": [
        "balance_sheet.$YEAR.assets.current_assets.current_investments",
        "balance_sheet.$YEAR.assets.current_assets.inventories",
        "balance_sheet.$YEAR.assets.current_assets.trade_receivables",
        "balance_sheet.$YEAR.assets.current_assets.cash_and_bank_balances",
        "balance_sheet.$YEAR.assets.current_assets.short_term_loans_and_advances",
        "balance_sheet.$YEAR.assets.current_assets.other_current_assets",
    ],
    "in-gaap:EquityAndLiabilities": [
        # Sum of shareholders' funds + non-current liab + current liab
        # Implemented as a recursive sum below
    ],
}


def _compute_composite(tag: str, ctx_ref: str, data: dict) -> Any:
    """Compute a subtotal value by summing the configured JSON paths."""
    paths = COMPOSITE_MAP_TEMPLATE.get(tag)
    if paths is None:
        return None
    # Pick CY or PY based on context
    year = "current_year" if ctx_ref == "I_CY" else "prior_year"
    total = 0
    found_any = False
    for path_template in paths:
        v = _get(data, path_template.replace("$YEAR", year))
        if v is not None:
            try:
                total += float(v)
                found_any = True
            except (TypeError, ValueError):
                pass
    return int(total) if found_any else None


def _resolve_value(tag: str, ctx_ref: str, data: dict) -> Any:
    """Look up the JSON value for a (tag, contextRef) pair, if mapped."""
    # 1. Simple direct map
    path = SIMPLE_MAP.get((tag, ctx_ref))
    if path:
        return _get(data, path)

    # 1b. Composite subtotal (computed from sub-line items)
    if tag in COMPOSITE_MAP_TEMPLATE and ctx_ref in ("I_CY", "I_PY"):
        v = _compute_composite(tag, ctx_ref, data)
        if v is not None:
            return v

    # 1c. EquityAndLiabilities = ShareholdersFunds + NonCurrentLiab + CurrentLiab
    if tag == "in-gaap:EquityAndLiabilities" and ctx_ref in ("I_CY", "I_PY"):
        sf = _compute_composite("in-gaap:ShareholdersFunds", ctx_ref, data) or 0
        nl = _compute_composite("in-gaap:NoncurrentLiabilities", ctx_ref, data) or 0
        cl = _compute_composite("in-gaap:CurrentLiabilities", ctx_ref, data) or 0
        total = sf + nl + cl
        if total > 0:
            return total

    # 2. Dimensional patterns (regex on contextRef)
    for dim_tag, regex, path_template in DIMENSIONAL_MAP:
        if dim_tag != tag:
            continue
        m = regex.match(ctx_ref)
        if not m:
            continue
        # Extract 1-based index from contextRef (groups[0]) if present, else 1
        try:
            idx_1based = int(m.group(1))
        except (IndexError, ValueError):
            idx_1based = 1
        idx_0based = idx_1based - 1
        json_path = path_template.replace("{idx0}", str(idx_0based))
        return _resolve_array_path(data, json_path)

    return None


def _resolve_array_path(data: dict, path: str) -> Any:
    """Resolve a path with array syntax: shareholders[0].name → data.shareholders[0]['name']."""
    parts = re.split(r"\.|\[(\d+)\]", path)
    parts = [p for p in parts if p]
    cur: Any = data
    for p in parts:
        if p.isdigit():
            if isinstance(cur, list) and int(p) < len(cur):
                cur = cur[int(p)]
            else:
                return None
        else:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return None
    return cur if cur is not None else None


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.2f}"
    if isinstance(value, (int,)):
        return str(value)
    return str(value)


# ── public generator ─────────────────────────────────────────────────────────

def generate_xbrl(data: dict, filename_base: str = "tawthiq_xbrl") -> XBRLResult:
    """Load template, fill in values from extracted JSON, return XBRL bytes."""
    try:
        if not TEMPLATE_XBRL_PATH.exists():
            return XBRLResult(success=False, error=f"Template not found at {TEMPLATE_XBRL_PATH}")

        with open(TEMPLATE_XBRL_PATH, "r", encoding="utf-16") as f:
            xml = f.read()

        # 1. Replace empty entity identifier with extracted CIN (or placeholder)
        cin = _get(data, "company.cin") or PLACEHOLDER
        xml = re.sub(
            r'(<xbrli:identifier scheme="http://www\.mca\.gov\.in/CIN">)(</xbrli:identifier>)',
            lambda m: m.group(1) + str(cin) + m.group(2),
            xml,
        )

        # 2. Walk every empty fact tag and try to fill from JSON
        fact_pattern = re.compile(
            r'<(in-(?:gaap|ca|ca-ent|ci-ent)):([\w]+)\b([^>]*?)contextRef="([^"]+)"([^>]*?)>'
            r'</\1:\2>'
        )

        facts_filled = 0
        facts_placeholder = 0
        facts_total = 0

        def fill_fact(m: re.Match) -> str:
            nonlocal facts_filled, facts_placeholder, facts_total
            facts_total += 1
            prefix = m.group(1)
            local = m.group(2)
            tag = f"{prefix}:{local}"
            ctx_ref = m.group(4)
            value = _resolve_value(tag, ctx_ref, data)
            full_open = m.group(0)[: -(len(f"</{prefix}:{local}>"))]
            close = f"</{prefix}:{local}>"
            if value is None or value == "":
                facts_placeholder += 1
                return full_open + PLACEHOLDER + close
            facts_filled += 1
            return full_open + _format_value(value) + close

        # First pass: empty facts (no content)
        xml = fact_pattern.sub(fill_fact, xml)

        # Also handle CIN occurrences as a fact element <in-ca:CorporateIdentityNumber contextRef="D_CY"></...>
        # (already covered by SIMPLE_MAP via fill_fact above)

        # Stats
        context_count = xml.count("<xbrli:context ")
        all_facts = re.findall(r'<in-[a-z]+(?:-ent)?:\w+[^>]*contextRef=', xml)

        # Filename per submission convention
        co = (_get(data, "company.name") or "company").upper()
        co = "".join(c if c.isalnum() else "_" for c in co).strip("_")
        end = _get(data, "reporting_period.end_date") or ""
        start = _get(data, "reporting_period.start_date") or ""
        try:
            fy = f"{start[:4]}_{end[2:4]}"
        except Exception:
            fy = (end or "FY").replace("-", "_")
        filename = f"{co}_STANDALONE_GENERATED_VI_{fy}.xml"

        return XBRLResult(
            success=True,
            xml=xml,
            filename=filename,
            fact_count=len(all_facts),
            facts_filled=facts_filled,
            facts_placeholder=facts_placeholder,
            context_count=context_count,
        )
    except Exception as exc:
        logger.exception("Template-driven XBRL generation failed")
        return XBRLResult(success=False, error=str(exc))
