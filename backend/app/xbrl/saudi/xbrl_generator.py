"""Emit Saudi-IFRS XBRL XML from a ResolvedFactSet.

Inputs:
  - facts    : ResolvedFactSet from source_mapper + ai_fallback
  - metadata : caller-supplied dict with the report-level fields needed
               to build contexts and units (entity_id, period_start_cy,
               period_end_cy, period_end_py, currency, …)
  - taxonomy : default Taxonomy (used for namespace info)

Output:
  XBRL XML string — well-formed, with one xbrli:context per period, one
  xbrli:unit per measurement basis, and one ifrs-full:... fact per real
  resolved concept.

NOT included (out of scope for this module):
  - schemaRef pointing at the actual filed taxonomy entry-point XSD
    (downstream caller can prepend that line for a specific filing).
  - linkbases (label / presentation / calculation) — not required for
    instance documents.
  - Footnotes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from xml.sax.saxutils import escape as xml_escape

from app.xbrl.saudi.source_mapper import (
    ResolvedFact,
    ResolvedFactSet,
)
from app.xbrl.saudi.taxonomy_loader import Taxonomy, default_taxonomy


# ── helpers ─────────────────────────────────────────────────────────────────

INSTANT_SECTIONS = {"balance_sheet"}
DURATION_SECTIONS = {"income_statement", "cash_flow", "changes_in_equity"}

# Concepts whose facts use per-share unit instead of plain currency.
PER_SHARE_TERMS = {"Basic EPS", "Diluted EPS"}
# Concepts that emit string text — no unitRef / decimals.
TEXT_TERMS = {
    "Company Name",
    "CR Number",
    "Auditor Name",
    "Audit Opinion",
    "Consolidated Financial Statements",
    "Unified Number",
    "Auditor License Number",
    "SAMA License Number",
}


@dataclass(frozen=True)
class XBRLMetadata:
    entity_id: str               # CR or unified-number used as scheme identifier
    entity_scheme: str = "http://www.cma.org.sa"
    period_start_cy: str = ""    # YYYY-MM-DD
    period_end_cy: str = ""
    period_end_py: str = ""
    period_start_py: str = ""    # optional, defaults to YYYY-01-01 if blank
    currency: str = "SAR"
    decimals_default: str = "0"  # "-3" if values are in thousands
    schema_ref: str = (
        "http://xbrl.ifrs.org/taxonomy/2024-03-27/full_ifrs/full_ifrs-cor_2024-03-27.xsd"
    )

    @staticmethod
    def from_dict(d: dict) -> "XBRLMetadata":
        return XBRLMetadata(
            entity_id=str(d.get("entity_id") or "0000000000"),
            entity_scheme=d.get("entity_scheme") or "http://www.cma.org.sa",
            period_start_cy=str(d.get("period_start_cy") or ""),
            period_end_cy=str(d.get("period_end_cy") or ""),
            period_end_py=str(d.get("period_end_py") or ""),
            period_start_py=str(d.get("period_start_py") or ""),
            currency=str(d.get("currency") or "SAR"),
            decimals_default=str(d.get("decimals_default") or "0"),
            schema_ref=str(
                d.get("schema_ref")
                or "http://xbrl.ifrs.org/taxonomy/2024-03-27/full_ifrs/full_ifrs-cor_2024-03-27.xsd"
            ),
        )


def _context_id_for(fact: ResolvedFact, year: str) -> str:
    """year is 'cy' or 'py'."""
    if fact.section_id in INSTANT_SECTIONS:
        return f"ctx_instant_{year}"
    return f"ctx_duration_{year}"


def _unit_id_for(fact: ResolvedFact, currency: str) -> str:
    if fact.business_term in PER_SHARE_TERMS:
        return f"u_{currency}_per_share"
    return f"u_{currency}"


def _is_text_concept(fact: ResolvedFact) -> bool:
    return fact.business_term in TEXT_TERMS


def _is_emittable(fact: ResolvedFact) -> bool:
    # Skip XBRL artifacts (Context / Unit / Local Extension) and unresolved.
    if fact.status != "found":
        return False
    if fact.xbrl_tag in ("Context", "Unit", "Local Extension"):
        return False
    return True


def _format_value(fact: ResolvedFact, value: Any) -> Optional[str]:
    if value is None:
        return None
    if _is_text_concept(fact):
        return xml_escape(str(value))
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    # String that should have been numeric — strip thousands separators
    s = str(value).strip()
    return xml_escape(s) if s else None


# ── XBRL fragments ──────────────────────────────────────────────────────────

def _build_contexts(meta: XBRLMetadata) -> str:
    """Emit exactly the four contexts our 57-concept taxonomy uses."""
    cy_start = meta.period_start_cy or (meta.period_end_cy[:4] + "-01-01" if meta.period_end_cy else "")
    py_start = meta.period_start_py or (meta.period_end_py[:4] + "-01-01" if meta.period_end_py else "")
    entity = (
        f"      <xbrli:entity>\n"
        f"        <xbrli:identifier scheme=\"{xml_escape(meta.entity_scheme)}\">"
        f"{xml_escape(meta.entity_id)}"
        f"</xbrli:identifier>\n"
        f"      </xbrli:entity>\n"
    )
    contexts = []
    if meta.period_end_cy:
        contexts.append(
            f"    <xbrli:context id=\"ctx_instant_cy\">\n"
            f"{entity}"
            f"      <xbrli:period>\n"
            f"        <xbrli:instant>{meta.period_end_cy}</xbrli:instant>\n"
            f"      </xbrli:period>\n"
            f"    </xbrli:context>"
        )
        if cy_start:
            contexts.append(
                f"    <xbrli:context id=\"ctx_duration_cy\">\n"
                f"{entity}"
                f"      <xbrli:period>\n"
                f"        <xbrli:startDate>{cy_start}</xbrli:startDate>\n"
                f"        <xbrli:endDate>{meta.period_end_cy}</xbrli:endDate>\n"
                f"      </xbrli:period>\n"
                f"    </xbrli:context>"
            )
    if meta.period_end_py:
        contexts.append(
            f"    <xbrli:context id=\"ctx_instant_py\">\n"
            f"{entity}"
            f"      <xbrli:period>\n"
            f"        <xbrli:instant>{meta.period_end_py}</xbrli:instant>\n"
            f"      </xbrli:period>\n"
            f"    </xbrli:context>"
        )
        if py_start:
            contexts.append(
                f"    <xbrli:context id=\"ctx_duration_py\">\n"
                f"{entity}"
                f"      <xbrli:period>\n"
                f"        <xbrli:startDate>{py_start}</xbrli:startDate>\n"
                f"        <xbrli:endDate>{meta.period_end_py}</xbrli:endDate>\n"
                f"      </xbrli:period>\n"
                f"    </xbrli:context>"
            )
    return "\n".join(contexts)


def _build_units(currency: str, needs_per_share: bool) -> str:
    units = [
        f"    <xbrli:unit id=\"u_{currency}\">\n"
        f"      <xbrli:measure>iso4217:{currency}</xbrli:measure>\n"
        f"    </xbrli:unit>"
    ]
    if needs_per_share:
        units.append(
            f"    <xbrli:unit id=\"u_{currency}_per_share\">\n"
            f"      <xbrli:divide>\n"
            f"        <xbrli:unitNumerator>\n"
            f"          <xbrli:measure>iso4217:{currency}</xbrli:measure>\n"
            f"        </xbrli:unitNumerator>\n"
            f"        <xbrli:unitDenominator>\n"
            f"          <xbrli:measure>xbrli:shares</xbrli:measure>\n"
            f"        </xbrli:unitDenominator>\n"
            f"      </xbrli:divide>\n"
            f"    </xbrli:unit>"
        )
    return "\n".join(units)


def _build_facts(facts: ResolvedFactSet, meta: XBRLMetadata) -> str:
    lines: list[str] = []
    needs_per_share = False
    for fact in facts.facts:
        if not _is_emittable(fact):
            continue
        is_text = _is_text_concept(fact)

        for year, value, period_present in (
            ("cy", fact.value_cy,
             bool(meta.period_end_cy)),
            ("py", fact.value_py,
             bool(meta.period_end_py)),
        ):
            if value is None or not period_present:
                continue
            value_str = _format_value(fact, value)
            if value_str is None:
                continue

            tag = fact.xbrl_tag
            ctx_id = _context_id_for(fact, year)

            if is_text:
                lines.append(
                    f"    <{tag} contextRef=\"{ctx_id}\">{value_str}</{tag}>"
                )
                continue

            unit_id = _unit_id_for(fact, meta.currency)
            if fact.business_term in PER_SHARE_TERMS:
                needs_per_share = True
            decimals = "2" if fact.business_term in PER_SHARE_TERMS else meta.decimals_default
            lines.append(
                f"    <{tag} contextRef=\"{ctx_id}\" unitRef=\"{unit_id}\" "
                f"decimals=\"{decimals}\">{value_str}</{tag}>"
            )
    return needs_per_share, "\n".join(lines)


def generate_xbrl(
    facts: ResolvedFactSet,
    metadata: dict | XBRLMetadata,
    taxonomy: Optional[Taxonomy] = None,
) -> str:
    """Build the XBRL instance document as an XML string."""
    if taxonomy is None:
        taxonomy = default_taxonomy()
    if isinstance(metadata, dict):
        meta = XBRLMetadata.from_dict(metadata)
    else:
        meta = metadata

    needs_per_share, facts_xml = _build_facts(facts, meta)
    contexts_xml = _build_contexts(meta)
    units_xml = _build_units(meta.currency, needs_per_share)

    # Namespaces — pick what we actually use
    nsmap = {
        "xbrli": "http://www.xbrl.org/2003/instance",
        "link": "http://www.xbrl.org/2003/linkbase",
        "xlink": "http://www.w3.org/1999/xlink",
        "iso4217": "http://www.xbrl.org/2003/iso4217",
        "ifrs-full": taxonomy.namespaces.get(
            "ifrs-full",
            "http://xbrl.ifrs.org/taxonomy/2024-03-27/ifrs-full",
        ),
        "socpa": taxonomy.namespaces.get(
            "socpa",
            "https://taxonomy.socpa.org.sa/socpa-extension/2024",
        ),
    }
    ns_attrs = "\n  ".join(f"xmlns:{prefix}=\"{uri}\"" for prefix, uri in nsmap.items())

    schema_ref_xml = (
        f"  <link:schemaRef xlink:type=\"simple\" "
        f"xlink:href=\"{xml_escape(meta.schema_ref)}\"/>"
    ) if meta.schema_ref else ""

    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<xbrli:xbrl\n"
        f"  {ns_attrs}>\n"
        "  <!-- Saudi-IFRS XBRL instance — generated by Tawthiq -->\n"
        + (f"\n{schema_ref_xml}\n" if schema_ref_xml else "")
        + "\n  <!-- ───── Contexts ───── -->\n"
        f"{contexts_xml}\n"
        "\n  <!-- ───── Units ───── -->\n"
        f"{units_xml}\n"
        "\n  <!-- ───── Facts ───── -->\n"
        f"{facts_xml}\n"
        "</xbrli:xbrl>\n"
    )
