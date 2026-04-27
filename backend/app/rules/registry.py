from dataclasses import dataclass, field
from enum import Enum
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


RULES: list[Rule] = [
    Rule(
        id="R01",
        name="Two Audit Firms Required",
        name_ar="شركتا تدقيق مطلوبتان",
        description="Banking & Insurance sectors must have two audit firms with signatures and stamps from both.",
        category=Category.AUDITOR,
        sector=Sector.BANKING_INSURANCE,
        severity=Severity.ERROR,
        validation_type=ValidationType.AI_JUDGMENT,
        ai_prompt="Count the distinct audit/accounting firms that signed this financial statement. List each firm name. Are there exactly TWO firms with visible signatures or stamps?",
    ),
    Rule(
        id="R02",
        name="Initial Notes Verification",
        name_ar="التحقق من الملاحظات الأولية",
        description="CR number, company name, and company activity in initial notes must match the PDF.",
        category=Category.CONTENT,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.FIELD_EXTRACTION,
        keywords=["CR", "سجل تجاري", "commercial registration", "company name", "activity"],
    ),
    Rule(
        id="R03",
        name="Auditor's Opinion Present",
        name_ar="وجود رأي المدقق",
        description="The PDF must contain the Auditor's Opinion section.",
        category=Category.AUDITOR,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.PRESENCE_CHECK,
        keywords=["auditor's opinion", "auditor opinion", "رأي المراجع", "رأي مراجع الحسابات", "independent auditor", "رأي المراجعين", "تقرير المراجع المستقل", "تقرير مراجع الحسابات", "independent auditors"],
        ai_prompt="Does this PDF contain an Independent Auditor's Opinion / Report section (in English or Arabic)? Look for section headings like 'Auditor Opinion', 'رأي المراجع', 'تقرير المراجع المستقل'. State the exact heading found.",
    ),
    Rule(
        id="R04",
        name="Basis of Opinion Present",
        name_ar="وجود أساس الرأي",
        description="The PDF must contain the Basis of Opinion section.",
        category=Category.AUDITOR,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.PRESENCE_CHECK,
        keywords=["basis of opinion", "basis for opinion", "أساس الرأي"],
    ),
    Rule(
        id="R05",
        name="Management Responsibilities Present",
        name_ar="وجود مسؤوليات الإدارة",
        description="The PDF must contain the Management Responsibilities section.",
        category=Category.AUDITOR,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.PRESENCE_CHECK,
        keywords=["management responsibilities", "responsibilities of management", "مسؤوليات الإدارة"],
    ),
    Rule(
        id="R06",
        name="Auditor's Responsibilities Present",
        name_ar="وجود مسؤوليات المدقق",
        description="The PDF must contain the Auditor's Responsibilities section.",
        category=Category.AUDITOR,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.PRESENCE_CHECK,
        keywords=["auditor's responsibilities", "responsibilities of the auditor", "مسؤوليات المراجع", "مسؤوليات مراجع الحسابات"],
    ),
    Rule(
        id="R07",
        name="No Handwritten Content",
        name_ar="عدم وجود محتوى مكتوب بخط اليد",
        description="No handwritten content allowed except for signatures.",
        category=Category.FORMAT,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.AI_JUDGMENT,
        ai_prompt="Visually inspect every page of this PDF. Is there ANY handwritten text, annotations, or markings other than signatures/stamps? Handwritten numbers, corrections, or notes count as handwriting.",
    ),
    Rule(
        id="R08",
        name="Mandatory Audit Fields Extraction",
        name_ar="استخراج حقول التدقيق الإلزامية",
        description="Partner name, audit firm name, and signing date must be extractable from the PDF.",
        category=Category.AUDITOR,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.FIELD_EXTRACTION,
        keywords=["partner", "audit firm", "signing date", "date of report", "شريك", "تاريخ التوقيع"],
        ai_prompt="Extract the following from this financial statement: 1) Name of the partner signing the report, 2) Name of the audit firm, 3) Date of signing the auditor report. Return each field or 'NOT FOUND' if missing.",
    ),
    Rule(
        id="R09",
        name="Signature Date and License Number",
        name_ar="تاريخ التوقيع ورقم الترخيص",
        description="Signature date must be present. License number of auditing firm checked if mentioned.",
        category=Category.AUDITOR,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.FIELD_EXTRACTION,
        keywords=["signature date", "license number", "رقم الترخيص", "تاريخ التوقيع"],
        ai_prompt="Find: 1) The date the auditor signed the report. 2) The license/registration number of the auditing firm (if mentioned). Return each value or 'NOT FOUND'.",
    ),
    Rule(
        id="R10",
        name="Filing Period Must Be Annual",
        name_ar="فترة الإيداع سنوية فقط",
        description="The filing period must be Annual. Quarterly statements are rejected.",
        category=Category.FORMAT,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.PATTERN_MATCH,
        keywords=["annual", "year ended", "سنوي", "السنة المنتهية", "twelve months", "12 months"],
    ),
    Rule(
        id="R11",
        name="Date Consistency Across Pages",
        name_ar="تناسق التاريخ عبر الصفحات",
        description="Dates on every page must match fiscal year and previous year periods.",
        category=Category.FINANCIAL,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.AI_JUDGMENT,
        ai_prompt="Check all fiscal year-end dates and comparative period dates across every financial statement page (balance sheet, income statement, cash flow, equity). Are the reporting period dates (e.g., 31 Dec 2025) and comparative dates (e.g., 31 Dec 2024) consistent across ALL statements? List any date mismatches found.",
    ),
    Rule(
        id="R12",
        name="Ministry of Commerce Registration",
        name_ar="التسجيل في وزارة التجارة",
        description="The company must be registered with the Ministry of Commerce.",
        category=Category.CONTENT,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.PRESENCE_CHECK,
        keywords=["ministry of commerce", "وزارة التجارة", "commercial registration", "سجل تجاري", "CR number", "CR no"],
    ),
    Rule(
        id="R13",
        name="Report Type Consistency",
        name_ar="تناسق نوع التقرير",
        description="Report type (company level/standalone vs consolidated) must match between PDF and initial form.",
        category=Category.CONTENT,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.FIELD_EXTRACTION,
        keywords=["consolidated", "company level", "standalone", "موحدة", "مستقلة"],
        ai_prompt="What type of financial report is this? Is it 'consolidated' or 'company level' (standalone)? Look at the title and headers of the financial statements.",
    ),
    Rule(
        id="R14",
        name="Currency Must Be SAR",
        name_ar="العملة يجب أن تكون ريال سعودي",
        description="Currency in financial statements must be exclusively SAR (Saudi Riyal).",
        category=Category.FINANCIAL,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.PATTERN_MATCH,
        keywords=["SAR", "Saudi Riyal", "ريال سعودي", "ريال"],
    ),
    Rule(
        id="R15",
        name="Reporting Scale Validation",
        name_ar="التحقق من مقياس التقرير",
        description="Financial reporting scale (thousands/millions/actuals) must match between PDF and initial form.",
        category=Category.FINANCIAL,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.FIELD_EXTRACTION,
        keywords=["thousands", "millions", "آلاف", "ملايين", "000", "000,000"],
        ai_prompt="What is the reporting unit/scale of the financial statements? Look for mentions of 'thousands', 'millions', zeros next to SAR, or 'in SAR' (which means actuals). Return: THOUSANDS, MILLIONS, or ACTUALS.",
    ),
    Rule(
        id="R16",
        name="Equity and Cash Flow Date Matching",
        name_ar="مطابقة تاريخ حقوق الملكية والتدفقات النقدية",
        description="For Banking/Insurance: Shareholder's Equity and Cash Flow dates must match the end year date in the initial form.",
        category=Category.SECTOR_SPECIFIC,
        sector=Sector.BANKING_INSURANCE,
        severity=Severity.ERROR,
        validation_type=ValidationType.AI_JUDGMENT,
        ai_prompt="Find the dates mentioned in: 1) The Statement of Changes in Shareholders' Equity, 2) The Statement of Cash Flows. What are the period end dates in each? Do they match?",
    ),
    Rule(
        id="R17",
        name="Notes Reference Validation",
        name_ar="التحقق من مراجع الملاحظات",
        description="If note numbers are mentioned in the PDF, they must be correct with corresponding page numbers.",
        category=Category.CONTENT,
        sector=Sector.ALL,
        severity=Severity.WARNING,
        validation_type=ValidationType.AI_JUDGMENT,
        ai_prompt="Check if the financial statements reference numbered notes. If note numbers are mentioned, verify they appear to be sequential and properly referenced. Are there any obvious gaps or errors in note numbering?",
    ),
    Rule(
        id="R18",
        name="NPO Financial Activity Matching",
        name_ar="مطابقة النشاط المالي للجمعيات",
        description="NPO sector: Financial activity in PDF must match the initial form. Verified from statement title and license number.",
        category=Category.SECTOR_SPECIFIC,
        sector=Sector.NPO,
        severity=Severity.ERROR,
        validation_type=ValidationType.FIELD_EXTRACTION,
        keywords=["financial activity", "نشاط مالي", "license number", "رقم الترخيص"],
        ai_prompt="For this NPO financial statement: 1) What financial activity is described? 2) What is the license number? Extract from the statement title and body.",
    ),
    Rule(
        id="R19",
        name="Initial Form Entries Validation",
        name_ar="التحقق من إدخالات النموذج الأولي",
        description="All fields entered in the initial form serve as validation criteria for document conformity.",
        category=Category.CONTENT,
        sector=Sector.ALL,
        severity=Severity.ERROR,
        validation_type=ValidationType.CONDITIONAL,
        keywords=[],
    ),
]


def get_rules(sector: str | None = None) -> list[Rule]:
    if sector is None:
        return RULES
    return [r for r in RULES if r.sector == Sector.ALL or r.sector.value == sector]
