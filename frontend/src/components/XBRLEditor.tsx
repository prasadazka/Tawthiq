import { useEffect, useMemo, useRef, useState } from "react";
import {
  validateXBRLXML,
  downloadEditedXBRL,
  type XMLValidationResponse,
  type XBRLValidationReport,
} from "../api";

interface Props {
  originalXml: string;
  filename: string;
  onBack: () => void;
  mcaReport?: XBRLValidationReport | null;
  extractedData?: Record<string, unknown> | null;
}

/* Map MCA validation rule_id → which XBRL tag the missing value belongs in.
   Lets us suggest the right tag for the user to add. */
const RULE_TO_XBRL_HINT: Record<string, { tag: string; context: string; placement: string }> = {
  IN_R01: { tag: 'xbrli:identifier scheme="http://www.mca.gov.in/CIN"', context: "(inside every <xbrli:entity>)", placement: "All contexts already include this — fill the CIN value between the opening and closing tag." },
  IN_R02: { tag: "in-ca:NameOfCompany", context: "D_CY", placement: "Inside the facts section." },
  IN_R03: { tag: "in-ca:AddressOfRegisteredOfficeOfCompany", context: "D_CY", placement: "Inside the facts section." },
  IN_R04: { tag: "in-ca:TypeOfIndustry", context: "D_CY", placement: "Inside the facts section." },
  IN_R09: { tag: "in-ca:NatureOfReportStandaloneConsolidated", context: "D_CY", placement: "Inside the facts section." },
  IN_R10: { tag: "in-gaap:Assets", context: "I_CY", placement: "With unitRef='INR' decimals='0' attributes." },
  IN_R11: { tag: "in-gaap:Assets", context: "I_PY", placement: "Prior-year balance sheet total." },
  IN_R12: { tag: "in-gaap:Assets / in-gaap:Equity / in-gaap:Liabilities", context: "I_CY", placement: "Verify Assets = Equity + Liabilities." },
  IN_R13: { tag: "in-gaap:Assets / in-gaap:Equity / in-gaap:Liabilities", context: "I_PY", placement: "Prior-year balance sheet equation." },
  IN_R14: { tag: "in-gaap:ShareCapital", context: "I_CY", placement: "With unitRef='INR' decimals='0'." },
  IN_R16: { tag: "in-gaap:RevenueFromOperations", context: "D_CY", placement: "With unitRef='INR' decimals='0'." },
  IN_R17: { tag: "in-gaap:ProfitLossForPeriod", context: "D_CY", placement: "With unitRef='INR' decimals='0'." },
  IN_R20: { tag: "in-gaap:ProfitLossForPeriod", context: "D_PY", placement: "Prior-year profit comparative." },
  IN_R21: { tag: "in-gaap:CashFlowsFromUsedInOperatingActivities / InvestingActivities / FinancingActivities", context: "D_CY", placement: "Three cash-flow sections." },
  IN_R23: { tag: "in-ca:TypeOfCashFlowStatement", context: "D_CY", placement: "Direct Method or Indirect Method." },
  IN_R24: { tag: "in-ca:NameOfAuditFirm", context: "AuditorsDomain_D_CY_3066_1_1", placement: "Inside auditor dimensional context." },
  IN_R25: { tag: "in-ca:NameOfAuditorSigningReport", context: "AuditorsDomain_D_CY_3066_1_1", placement: "Inside auditor dimensional context." },
  IN_R26: { tag: "in-ca:MembershipNumberOfAuditorOrAuditorsRepresentative", context: "AuditorsDomain_D_CY_3066_1_1", placement: "Inside auditor dimensional context." },
  IN_R27: { tag: "in-ca:DateOfSigningAuditReportByAuditors", context: "AuditorsDomain_D_CY_3066_1_1", placement: "Must be after fiscal year-end." },
  IN_R30: { tag: "in-ca:DateOfBoardMeetingWhenFinalAccountsWereApproved", context: "D_CY", placement: "Date in YYYY-MM-DD format." },
  IN_R33: { tag: "in-ca:LevelOfRoundingUsedInFinancialStatements", context: "D_CY", placement: "Actual / Thousands / Lakhs / Millions / Crores." },
};

export default function XBRLEditor({
  originalXml,
  filename,
  onBack,
  mcaReport,
  extractedData: _extractedData,
}: Props) {
  const [xml, setXml] = useState(originalXml);
  const [validation, setValidation] = useState<XMLValidationResponse | null>(null);
  const [validating, setValidating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [activePanel, setActivePanel] = useState<"gaps" | "issues" | "empty" | "diff">("gaps");
  const [flashLine, setFlashLine] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineNumbersRef = useRef<HTMLDivElement>(null);

  // Auto-validate on first load
  useEffect(() => {
    runValidation(originalXml);
  }, [originalXml]);

  // Track changed lines (basic line-by-line diff)
  const changedLines = useMemo(() => {
    const origLines = originalXml.split("\n");
    const curLines = xml.split("\n");
    const changed = new Set<number>();
    const max = Math.max(origLines.length, curLines.length);
    for (let i = 0; i < max; i++) {
      if (origLines[i] !== curLines[i]) changed.add(i + 1);
    }
    return changed;
  }, [xml, originalXml]);

  const lineCount = useMemo(() => xml.split("\n").length, [xml]);

  const runValidation = async (currentXml: string) => {
    setValidating(true);
    try {
      const result = await validateXBRLXML(currentXml);
      setValidation(result);
    } catch (err) {
      console.error("Validation failed:", err);
    } finally {
      setValidating(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const blob = await downloadEditedXBRL(xml, filename);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("Download failed: " + (err instanceof Error ? err.message : err));
    } finally {
      setDownloading(false);
    }
  };

  // Scroll editor to a specific line (with a brief flash on the line number)
  const jumpToLine = (line: number) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const lines = xml.split("\n");
    const safeLine = Math.max(1, Math.min(line, lines.length));
    let pos = 0;
    for (let i = 0; i < safeLine - 1; i++) {
      pos += lines[i].length + 1;
    }
    const lineLen = lines[safeLine - 1]?.length ?? 0;

    ta.focus({ preventScroll: true });
    ta.setSelectionRange(pos, pos + lineLen);

    // Centre the line vertically in the visible area
    const lineHeight = parseFloat(getComputedStyle(ta).lineHeight) || 18;
    const targetTop = Math.max(0, (safeLine - 1) * lineHeight - ta.clientHeight / 2);
    ta.scrollTop = targetTop;
    if (lineNumbersRef.current) lineNumbersRef.current.scrollTop = targetTop;

    // Flash the line number for visual confirmation
    setFlashLine(safeLine);
    window.setTimeout(() => setFlashLine(null), 1500);
  };

  // Sync line-number gutter scroll with textarea
  const handleScroll = () => {
    if (textareaRef.current && lineNumbersRef.current) {
      lineNumbersRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  };

  const errorCount = validation?.errors.length ?? 0;
  const warningCount = validation?.warnings.length ?? 0;
  const emptyCount = validation?.empty_facts.length ?? 0;
  const canDownload = !!validation && validation.valid && !validating;

  /* MCA-level gaps: rules from the 33-rule MCA validator that the source PDF
     couldn't satisfy (e.g., CIN absent, address absent). These don't appear in
     XML validation because the missing data simply isn't in the generated XML
     at all — but the user still needs to know about and fill them in. */
  const mcaGaps = useMemo(() => {
    if (!mcaReport) return [];
    return [...mcaReport.blocking_failures, ...mcaReport.warnings].map((f) => ({
      rule_id: f.rule_id,
      name: f.name,
      message: f.message,
      hint: RULE_TO_XBRL_HINT[f.rule_id],
    }));
  }, [mcaReport]);

  // Pull the first concrete tag name from a hint like "in-gaap:Assets / in-gaap:Equity"
  // or "xbrli:identifier scheme=..." → returns null for non-insertable hints (multi-tag,
  // identifier, etc.) and the user is asked to jump manually.
  const extractInsertableTag = (rawTag: string): string | null => {
    if (rawTag.includes("/")) return null;            // multi-tag hints — too ambiguous
    if (rawTag.startsWith("xbrli:")) return null;     // entity/identifier — not a fact
    const tag = rawTag.split(" ")[0];                 // drop attribute hints
    if (!tag.includes(":")) return null;              // missing namespace
    return tag;
  };

  // For a given hint, find the first matching tag+context in the XML.
  // Returns the 1-indexed line number if found, else 0.
  const findExistingTagLine = (rawTag: string, context: string): number => {
    const tag = extractInsertableTag(rawTag);
    if (!tag) return 0;
    const escTag = tag.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
    const escCtx = context.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
    const re = new RegExp(`<${escTag}\\b[^>]*contextRef="${escCtx}"`);
    const m = re.exec(xml);
    if (!m) return 0;
    return xml.slice(0, m.index).split("\n").length;
  };

  const insertPlaceholderTag = (hint: { tag: string; context: string }) => {
    const ta = textareaRef.current;
    if (!ta) return;

    // 1. If a matching tag already exists in the XML, jump to it instead of duplicating
    const existingLine = findExistingTagLine(hint.tag, hint.context);
    if (existingLine > 0) {
      jumpToLine(existingLine);
      return;
    }

    // 2. Build a single-tag placeholder. Skip if the hint isn't unambiguous.
    const tagOnly = extractInsertableTag(hint.tag);
    if (!tagOnly) {
      // Multi-tag or special — just inform the user.
      window.alert(
        `This rule covers multiple tags (${hint.tag}). ` +
        `Locate them in the XML and fill values manually.`
      );
      return;
    }

    const snippet = `\n    <${tagOnly} contextRef="${hint.context}">FILL_VALUE_HERE</${tagOnly}>`;
    // Insert before the closing </xbrli:xbrl> so we don't break the document
    const closeIdx = xml.lastIndexOf("</xbrli:xbrl>");
    const insertAt = closeIdx > 0 ? closeIdx : xml.length;
    const newXml = xml.slice(0, insertAt) + snippet + "\n" + xml.slice(insertAt);
    setXml(newXml);

    // Highlight the placeholder so the user can immediately type the value
    const placeholderPos = insertAt + snippet.indexOf("FILL_VALUE_HERE");
    window.setTimeout(() => {
      ta.focus();
      ta.setSelectionRange(placeholderPos, placeholderPos + "FILL_VALUE_HERE".length);
      const line = newXml.slice(0, placeholderPos).split("\n").length;
      const lineHeight = parseFloat(getComputedStyle(ta).lineHeight) || 18;
      ta.scrollTop = Math.max(0, (line - 1) * lineHeight - ta.clientHeight / 2);
      if (lineNumbersRef.current) lineNumbersRef.current.scrollTop = ta.scrollTop;
      setFlashLine(line);
      window.setTimeout(() => setFlashLine(null), 1500);
    }, 50);
  };

  return (
    <div className="xbrl-editor">
      {/* Header */}
      <div className="editor-header">
        <div>
          <h3 className="editor-title">Review &amp; Edit XBRL</h3>
          <p className="editor-sub">{filename}</p>
        </div>
        <div className="editor-actions">
          <button type="button" className="btn btn-outline btn-sm" onClick={onBack}>
            Back
          </button>
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={() => runValidation(xml)}
            disabled={validating}
          >
            {validating ? "Validating..." : "Re-validate"}
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handleDownload}
            disabled={!canDownload || downloading}
            title={canDownload ? "Download XBRL" : "Fix all errors to enable download"}
          >
            {downloading ? "Downloading..." : "Download XBRL"}
          </button>
        </div>
      </div>

      {/* Status bar */}
      <div className="editor-status">
        <div className={`status-pill ${validation?.well_formed ? "status-ok" : "status-err"}`}>
          {validation?.well_formed ? "Well-formed XML" : "XML parse error"}
        </div>
        <div className={`status-pill ${errorCount === 0 ? "status-ok" : "status-err"}`}>
          {errorCount} error{errorCount !== 1 && "s"}
        </div>
        <div className={`status-pill ${warningCount === 0 ? "status-ok" : "status-warn"}`}>
          {warningCount} warning{warningCount !== 1 && "s"}
        </div>
        <div className={`status-pill ${emptyCount === 0 ? "status-ok" : "status-warn"}`}>
          {emptyCount} empty field{emptyCount !== 1 && "s"}
        </div>
        <div className={`status-pill ${changedLines.size === 0 ? "status-info" : "status-edit"}`}>
          {changedLines.size} edited line{changedLines.size !== 1 && "s"}
        </div>
        {validation?.stats && (
          <div className="status-pill status-info">
            {validation.stats.facts} facts / {validation.stats.contexts} contexts
          </div>
        )}
      </div>

      {/* Editor + side panel */}
      <div className="editor-body">
        <div className="editor-main">
          <div className="editor-line-numbers" ref={lineNumbersRef}>
            {Array.from({ length: lineCount }, (_, i) => i + 1).map((n) => {
              const classes = ["ln-row"];
              if (changedLines.has(n)) classes.push("ln-edited");
              if (flashLine === n) classes.push("ln-flash");
              return (
                <div key={n} className={classes.join(" ")}>
                  {n}
                </div>
              );
            })}
          </div>
          <textarea
            ref={textareaRef}
            className="editor-textarea"
            aria-label="XBRL XML editor"
            value={xml}
            onChange={(e) => setXml(e.target.value)}
            onScroll={handleScroll}
            spellCheck={false}
            wrap="off"
          />
        </div>

        <div className="editor-side">
          <div className="side-tabs">
            <button
              type="button"
              className={`side-tab ${activePanel === "gaps" ? "side-tab-active" : ""}`}
              onClick={() => setActivePanel("gaps")}
            >
              Gaps ({mcaGaps.length})
            </button>
            <button
              type="button"
              className={`side-tab ${activePanel === "issues" ? "side-tab-active" : ""}`}
              onClick={() => setActivePanel("issues")}
            >
              XML ({errorCount + warningCount})
            </button>
            <button
              type="button"
              className={`side-tab ${activePanel === "empty" ? "side-tab-active" : ""}`}
              onClick={() => setActivePanel("empty")}
            >
              Empty ({emptyCount})
            </button>
            <button
              type="button"
              className={`side-tab ${activePanel === "diff" ? "side-tab-active" : ""}`}
              onClick={() => setActivePanel("diff")}
            >
              Edits ({changedLines.size})
            </button>
          </div>

          <div className="side-content">
            {activePanel === "gaps" && (
              <>
                {mcaGaps.length === 0 && (
                  <p className="side-ok">No MCA gaps — all 33 source-data rules satisfied.</p>
                )}
                {mcaGaps.length > 0 && (
                  <p className="side-help">
                    These fields couldn't be extracted from the PDF. Click any item to insert a
                    placeholder tag in the XML at your cursor position, then type the value.
                  </p>
                )}
                {mcaGaps.map((g) => {
                  const existingLine = g.hint ? findExistingTagLine(g.hint.tag, g.hint.context) : 0;
                  const canInsert = g.hint && extractInsertableTag(g.hint.tag) !== null;
                  return (
                    <div className="gap-item" key={g.rule_id}>
                      <div className="gap-head">
                        <span className="gap-id">{g.rule_id}</span>
                        <span className="gap-name">{g.name}</span>
                        {existingLine > 0 && (
                          <span className="gap-pill-present">In XML (line {existingLine})</span>
                        )}
                      </div>
                      <p className="gap-msg">{g.message}</p>
                      {g.hint && (
                        <>
                          <div className="gap-tag-info">
                            <span className="gap-tag-label">XBRL tag:</span>
                            <code className="gap-tag">{g.hint.tag}</code>
                            <span className="gap-tag-label">context:</span>
                            <code className="gap-tag">{g.hint.context}</code>
                          </div>
                          <p className="gap-placement">{g.hint.placement}</p>
                          <button
                            type="button"
                            className="gap-insert-btn"
                            onClick={() => insertPlaceholderTag(g.hint!)}
                          >
                            {existingLine > 0
                              ? `→ Jump to line ${existingLine}`
                              : canInsert
                              ? "+ Insert placeholder tag"
                              : "Find in XML"}
                          </button>
                        </>
                      )}
                    </div>
                  );
                })}
              </>
            )}

            {activePanel === "issues" && (
              <>
                {!validation && <p className="side-empty">Validating...</p>}
                {validation && errorCount === 0 && warningCount === 0 && (
                  <p className="side-ok">No issues. XML is valid and ready to download.</p>
                )}
                {validation?.errors.map((e, i) => (
                  <button
                    type="button"
                    key={`e${i}`}
                    className="issue-item issue-error"
                    onClick={() => e.line && jumpToLine(e.line)}
                  >
                    <span className="issue-code">{e.code}</span>
                    <span className="issue-msg">{e.message}</span>
                    {e.line && <span className="issue-line">line {e.line}</span>}
                  </button>
                ))}
                {validation?.warnings.map((w, i) => (
                  <button
                    type="button"
                    key={`w${i}`}
                    className="issue-item issue-warning"
                    onClick={() => w.line && jumpToLine(w.line)}
                  >
                    <span className="issue-code">{w.code}</span>
                    <span className="issue-msg">{w.message}</span>
                    {w.line && <span className="issue-line">line {w.line}</span>}
                  </button>
                ))}
              </>
            )}

            {activePanel === "empty" && (
              <>
                {emptyCount === 0 && (
                  <p className="side-ok">No empty fields — every tagged fact has a value.</p>
                )}
                {validation?.empty_facts.map((f, i) => (
                  <button
                    type="button"
                    key={`f${i}`}
                    className="empty-item"
                    onClick={() => jumpToLine(f.line)}
                  >
                    <div className="empty-tag">{f.tag}</div>
                    <div className="empty-meta">
                      <span className="empty-ctx">{f.context_ref}</span>
                      <span className="empty-line">line {f.line}</span>
                    </div>
                  </button>
                ))}
              </>
            )}

            {activePanel === "diff" && (
              <>
                {changedLines.size === 0 && (
                  <p className="side-empty">No edits yet. The XML matches the generated original.</p>
                )}
                {changedLines.size > 0 && (
                  <>
                    <p className="side-help">{changedLines.size} line(s) modified. Click any line to jump.</p>
                    {Array.from(changedLines).slice(0, 50).map((line) => (
                      <button
                        type="button"
                        key={line}
                        className="diff-item"
                        onClick={() => jumpToLine(line)}
                      >
                        <span className="diff-line">line {line}</span>
                        <span className="diff-preview">
                          {(xml.split("\n")[line - 1] || "").trim().slice(0, 60)}
                        </span>
                      </button>
                    ))}
                    {changedLines.size > 50 && (
                      <p className="side-help">…and {changedLines.size - 50} more</p>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
