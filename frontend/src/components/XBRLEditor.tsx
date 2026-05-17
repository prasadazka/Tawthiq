import { useEffect, useMemo, useRef, useState } from "react";
import { validateXBRLXML, downloadEditedXBRL, type XMLValidationResponse } from "../api";

interface Props {
  originalXml: string;
  filename: string;
  onBack: () => void;
}

export default function XBRLEditor({ originalXml, filename, onBack }: Props) {
  const [xml, setXml] = useState(originalXml);
  const [validation, setValidation] = useState<XMLValidationResponse | null>(null);
  const [validating, setValidating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [activePanel, setActivePanel] = useState<"issues" | "empty" | "diff">("issues");
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

  // Scroll editor to a specific line
  const jumpToLine = (line: number) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const lines = xml.split("\n");
    let pos = 0;
    for (let i = 0; i < line - 1 && i < lines.length; i++) {
      pos += lines[i].length + 1;
    }
    ta.focus();
    ta.setSelectionRange(pos, pos + (lines[line - 1]?.length || 0));
    // Scroll the textarea so the line is visible
    const lineHeight = parseFloat(getComputedStyle(ta).lineHeight) || 18;
    ta.scrollTop = (line - 1) * lineHeight - ta.clientHeight / 2;
    // Mirror to line-number gutter
    if (lineNumbersRef.current) lineNumbersRef.current.scrollTop = ta.scrollTop;
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
            {Array.from({ length: lineCount }, (_, i) => i + 1).map((n) => (
              <div key={n} className={`ln-row ${changedLines.has(n) ? "ln-edited" : ""}`}>
                {n}
              </div>
            ))}
          </div>
          <textarea
            ref={textareaRef}
            className="editor-textarea"
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
              className={`side-tab ${activePanel === "issues" ? "side-tab-active" : ""}`}
              onClick={() => setActivePanel("issues")}
            >
              Issues ({errorCount + warningCount})
            </button>
            <button
              type="button"
              className={`side-tab ${activePanel === "empty" ? "side-tab-active" : ""}`}
              onClick={() => setActivePanel("empty")}
            >
              Missing ({emptyCount})
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
