"""Generic XBRL XML structural validator.

Used after the user (potentially) edits the generated XBRL XML in the UI,
before download. Catches:
  - XML well-formedness errors (unclosed tags, malformed attributes, etc.)
  - Missing required XBRL elements (root, schemaRef, contexts, units, facts)
  - Facts with empty values (i.e., Gemini didn't extract a value the user
    might want to fill in manually)
  - Orphan contextRef / unitRef references (point to undeclared ids)

Country-agnostic: country-specific element-presence rules can be added later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET


@dataclass
class XMLValidationIssue:
    severity: str          # "error" | "warning" | "info"
    code: str              # short stable code, e.g. "XML_PARSE_ERROR"
    message: str
    line: int | None = None
    column: int | None = None
    element: str | None = None  # XML element name, when applicable


@dataclass
class EmptyFact:
    tag: str               # e.g., "in-gaap:Assets"
    context_ref: str       # e.g., "I_CY"
    line: int              # 1-indexed line number in the XML
    raw_xml: str           # the original tag snippet


@dataclass
class XMLValidationReport:
    well_formed: bool
    valid: bool                                  # well_formed AND no errors
    issues: list[XMLValidationIssue] = field(default_factory=list)
    empty_facts: list[EmptyFact] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> list[XMLValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[XMLValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


class XBRLXMLValidator:
    """Validate the structure of an XBRL XML string."""

    XBRLI_NS = "http://www.xbrl.org/2003/instance"
    LINK_NS = "http://www.xbrl.org/2003/linkbase"

    def validate(self, xml_text: str) -> XMLValidationReport:
        report = XMLValidationReport(well_formed=False, valid=False)

        # 1. Try to parse — catches unclosed tags, bad attributes, etc.
        try:
            root = ET.fromstring(xml_text)
            report.well_formed = True
        except ET.ParseError as exc:
            # exc.position is (line, col), 1-indexed
            line = getattr(exc, "position", (None, None))[0]
            col = getattr(exc, "position", (None, None))[1]
            report.issues.append(XMLValidationIssue(
                severity="error",
                code="XML_PARSE_ERROR",
                message=f"Malformed XML: {exc}",
                line=line,
                column=col,
            ))
            return report

        # 2. Root element check
        if not root.tag.endswith("xbrl") or self.XBRLI_NS not in root.tag:
            report.issues.append(XMLValidationIssue(
                severity="error",
                code="MISSING_ROOT",
                message=f"Root element must be {{{self.XBRLI_NS}}}xbrl, got {root.tag}",
                element=root.tag,
            ))

        # 3. schemaRef
        schema_refs = root.findall(f"{{{self.LINK_NS}}}schemaRef")
        if not schema_refs:
            report.issues.append(XMLValidationIssue(
                severity="error",
                code="MISSING_SCHEMA_REF",
                message="No <link:schemaRef> element found — taxonomy reference is mandatory",
            ))

        # 4. Contexts
        contexts = root.findall(f"{{{self.XBRLI_NS}}}context")
        context_ids = {c.get("id") for c in contexts if c.get("id")}
        if not contexts:
            report.issues.append(XMLValidationIssue(
                severity="error",
                code="NO_CONTEXTS",
                message="No <xbrli:context> elements found — at least one required",
            ))
        # Check each context has entity + period
        for ctx in contexts:
            cid = ctx.get("id", "?")
            if ctx.find(f"{{{self.XBRLI_NS}}}entity") is None:
                report.issues.append(XMLValidationIssue(
                    severity="error",
                    code="CONTEXT_NO_ENTITY",
                    message=f"Context '{cid}' missing <xbrli:entity>",
                    element=cid,
                ))
            if ctx.find(f"{{{self.XBRLI_NS}}}period") is None:
                report.issues.append(XMLValidationIssue(
                    severity="error",
                    code="CONTEXT_NO_PERIOD",
                    message=f"Context '{cid}' missing <xbrli:period>",
                    element=cid,
                ))

        # 5. Units
        units = root.findall(f"{{{self.XBRLI_NS}}}unit")
        unit_ids = {u.get("id") for u in units if u.get("id")}
        if not units:
            report.issues.append(XMLValidationIssue(
                severity="warning",
                code="NO_UNITS",
                message="No <xbrli:unit> elements found — numeric facts cannot be expressed",
            ))

        # 6. Facts + reference checks + empty value detection
        fact_count = 0
        empty_count = 0
        orphan_ctx_refs: set[str] = set()
        orphan_unit_refs: set[str] = set()

        for elem in root.iter():
            ns = elem.tag.split("}", 1)[0].lstrip("{") if "}" in elem.tag else ""
            local = elem.tag.split("}", 1)[-1]
            # Skip xbrli, link, xbrldi structural elements
            if ns in (self.XBRLI_NS, self.LINK_NS) or "xbrldi" in ns:
                continue
            ctx_ref = elem.get("contextRef")
            if ctx_ref is None:
                continue  # not a fact
            fact_count += 1

            # Check that contextRef points to a real context
            if ctx_ref not in context_ids:
                orphan_ctx_refs.add(ctx_ref)

            # Check unitRef if present
            unit_ref = elem.get("unitRef")
            if unit_ref and unit_ref not in unit_ids:
                orphan_unit_refs.add(unit_ref)

            # Empty value check
            text = (elem.text or "").strip()
            if not text:
                empty_count += 1
                # Find original tag snippet from xml_text for display
                snippet = self._find_snippet(xml_text, local, ctx_ref)
                report.empty_facts.append(EmptyFact(
                    tag=f"{self._prefix_for_ns(ns, xml_text)}:{local}",
                    context_ref=ctx_ref,
                    line=snippet["line"],
                    raw_xml=snippet["text"],
                ))

        if orphan_ctx_refs:
            report.issues.append(XMLValidationIssue(
                severity="error",
                code="ORPHAN_CONTEXT_REF",
                message=f"{len(orphan_ctx_refs)} fact(s) reference undeclared context(s): {sorted(orphan_ctx_refs)}",
            ))
        if orphan_unit_refs:
            report.issues.append(XMLValidationIssue(
                severity="error",
                code="ORPHAN_UNIT_REF",
                message=f"Fact(s) reference undeclared unit(s): {sorted(orphan_unit_refs)}",
            ))
        if empty_count > 0:
            report.issues.append(XMLValidationIssue(
                severity="warning",
                code="EMPTY_FACT_VALUES",
                message=f"{empty_count} fact(s) have empty values — fill them in or remove the tags",
            ))
        if fact_count == 0:
            report.issues.append(XMLValidationIssue(
                severity="error",
                code="NO_FACTS",
                message="No data facts found in the document",
            ))

        report.stats = {
            "contexts": len(contexts),
            "units": len(units),
            "facts": fact_count,
            "empty_facts": empty_count,
        }
        report.valid = report.well_formed and not report.errors
        return report

    # ── helpers ──────────────────────────────────────────────────────────────

    def _prefix_for_ns(self, ns: str, xml_text: str) -> str:
        """Find the xmlns prefix declared for a namespace URI in the document."""
        m = re.search(rf'xmlns:(\w[\w-]*)="{re.escape(ns)}"', xml_text)
        return m.group(1) if m else "ns"

    def _find_snippet(self, xml_text: str, local_name: str, ctx_ref: str) -> dict:
        """Find the first occurrence of the tag with this contextRef and return
        the surrounding line + 1-indexed line number."""
        pattern = re.compile(
            rf'<[^>]*:{re.escape(local_name)}\b[^>]*contextRef="{re.escape(ctx_ref)}"[^>]*>[^<]*</[^>]*:{re.escape(local_name)}>'
        )
        m = pattern.search(xml_text)
        if not m:
            return {"line": 0, "text": ""}
        line_no = xml_text[: m.start()].count("\n") + 1
        return {"line": line_no, "text": m.group(0)}
