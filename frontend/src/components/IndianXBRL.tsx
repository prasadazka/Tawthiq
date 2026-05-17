import { useState } from "react";
import UploadZone from "./UploadZone";
import XBRLEditor from "./XBRLEditor";
import {
  extractIndianXBRL,
  generateIndianXBRL,
  type XBRLExtractResponse,
  type XBRLValidationReport,
} from "../api";

type Stage = "idle" | "extracting" | "validated" | "generating" | "blocked" | "editing" | "error";

interface GeneratedFile {
  blob: Blob;
  filename: string;
  factCount: number;
  contextCount: number;
  warnings: number;
  elapsedSeconds: number;
  xmlText: string;   // decoded UTF-16 text for editor
}

export default function IndianXBRL() {
  const [stage, setStage] = useState<Stage>("idle");
  const [fileName, setFileName] = useState("");
  const [fileSize, setFileSize] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [extractData, setExtractData] = useState<XBRLExtractResponse | null>(null);
  const [validationReport, setValidationReport] = useState<XBRLValidationReport | null>(null);
  const [generated, setGenerated] = useState<GeneratedFile | null>(null);
  const [error, setError] = useState<string>("");
  const [skipValidation, setSkipValidation] = useState(false);

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFile = async (file: File) => {
    setPdfFile(file);
    setFileName(file.name);
    setFileSize(formatSize(file.size));
    setError("");
    setStage("extracting");

    try {
      const data = await extractIndianXBRL(file);
      setExtractData(data);
      setValidationReport(data.validation);
      setStage("validated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed");
      setStage("error");
    }
  };

  const handleGenerate = async (forceSkip: boolean = false) => {
    if (!pdfFile) return;
    setStage("generating");
    setError("");

    try {
      const result = await generateIndianXBRL(pdfFile, forceSkip || skipValidation);

      if ("blob" in result) {
        // Decode the UTF-16 XML so the editor can show it as text
        const buf = await result.blob.arrayBuffer();
        const xmlText = new TextDecoder("utf-16").decode(buf);
        setGenerated({ ...result, xmlText });
        setStage("editing");
      } else {
        setValidationReport(result.validationReport);
        setStage("blocked");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
      setStage("error");
    }
  };

  const handleReset = () => {
    setStage("idle");
    setExtractData(null);
    setValidationReport(null);
    setGenerated(null);
    setError("");
    setFileName("");
    setFileSize("");
    setPdfFile(null);
    setSkipValidation(false);
  };

  return (
    <div className="indian-xbrl">
      {/* IDLE */}
      {stage === "idle" && (
        <div className="landing">
          <div className="hero">
            <h1>Indian XBRL<br />Generation</h1>
            <p className="hero-sub">
              Upload an Indian company's audit report PDF. Tawthiq extracts financial data,
              validates against MCA filing requirements, and generates a ready-to-submit
              XBRL XML file.
            </p>
          </div>
          <UploadZone onFileSelected={handleFile} />
          <div className="features">
            <div className="feature">
              <div className="feature-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
              </div>
              <h3>Gemini Data Extraction</h3>
              <p>Reads scanned PDFs and extracts balance sheet, P&amp;L, cash flow, directors, shareholders into structured JSON.</p>
            </div>
            <div className="feature">
              <div className="feature-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <h3>33 MCA Validation Rules</h3>
              <p>Balance sheet equation, CIN format, DIN validation, audit date checks, and more — before generating XBRL.</p>
            </div>
            <div className="feature">
              <div className="feature-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <polyline points="8 17 12 21 16 17" />
                  <line x1="12" y1="12" x2="12" y2="21" />
                  <path d="M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29" />
                </svg>
              </div>
              <h3>XBRL XML Download</h3>
              <p>Generated XBRL uses ICAI in-gaap + in-ca taxonomy, UTF-16 encoded, ready for MCA iXBRL portal upload.</p>
            </div>
          </div>
        </div>
      )}

      {/* EXTRACTING */}
      {stage === "extracting" && (
        <div className="validating-card">
          <div className="validating-file">
            <div className="file-thumb">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
            </div>
            <div>
              <p className="validating-name">{fileName}</p>
              <p className="validating-size">{fileSize}</p>
            </div>
          </div>
          <div className="progress-section">
            <div className="progress-bar"><div className="progress-fill" /></div>
            <p className="progress-label">Extracting financial data with Gemini AI (~60s)...</p>
          </div>
          <div className="validating-steps">
            <div className="step step-done">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 12l2 2 4-4" /><circle cx="12" cy="12" r="10" />
              </svg>
              File uploaded
            </div>
            <div className="step step-active">
              <div className="step-spinner" />
              Reading PDF + extracting to JSON
            </div>
            <div className="step step-pending">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="10" /></svg>
              Validating against 33 MCA rules
            </div>
            <div className="step step-pending">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="10" /></svg>
              Generate XBRL XML
            </div>
          </div>
        </div>
      )}

      {/* VALIDATED — show report, let user generate */}
      {stage === "validated" && extractData && validationReport && (
        <ValidationView
          fileName={fileName}
          fileSize={fileSize}
          extractData={extractData}
          report={validationReport}
          skipValidation={skipValidation}
          onSkipChange={setSkipValidation}
          onGenerate={() => handleGenerate(false)}
          onReset={handleReset}
        />
      )}

      {/* GENERATING */}
      {stage === "generating" && (
        <div className="validating-card">
          <div className="progress-section">
            <div className="progress-bar"><div className="progress-fill" /></div>
            <p className="progress-label">Generating XBRL XML document...</p>
          </div>
        </div>
      )}

      {/* BLOCKED — validation failed, can't proceed without skip */}
      {stage === "blocked" && validationReport && (
        <BlockedView
          report={validationReport}
          onForceGenerate={() => handleGenerate(true)}
          onReset={handleReset}
        />
      )}

      {/* EDITING — review and edit XBRL before download */}
      {stage === "editing" && generated && (
        <XBRLEditor
          originalXml={generated.xmlText}
          filename={generated.filename}
          onBack={handleReset}
        />
      )}

      {/* ERROR */}
      {stage === "error" && (
        <div className="error-card">
          <div className="error-icon-wrap">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2">
              <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <h3>Operation Failed</h3>
          <p className="error-msg">{error}</p>
          <button type="button" className="btn btn-primary" onClick={handleReset}>Try Again</button>
        </div>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────────────────

function ValidationView({
  fileName,
  fileSize,
  extractData,
  report,
  skipValidation,
  onSkipChange,
  onGenerate,
  onReset,
}: {
  fileName: string;
  fileSize: string;
  extractData: XBRLExtractResponse;
  report: XBRLValidationReport;
  skipValidation: boolean;
  onSkipChange: (v: boolean) => void;
  onGenerate: () => void;
  onReset: () => void;
}) {
  const data = extractData.extraction.data as Record<string, any>;
  const passRate = Math.round((report.summary.pass / (report.summary.pass + report.summary.fail || 1)) * 100);

  return (
    <div className="xbrl-results">
      <div className="xbrl-header">
        <div>
          <h2 className="xbrl-title">Extraction &amp; Validation Complete</h2>
          <p className="xbrl-meta">
            {fileName} &middot; {fileSize} &middot; {extractData.extraction.page_count} pages &middot; {extractData.timings.total_seconds}s
          </p>
        </div>
        <button type="button" className="btn btn-outline btn-sm" onClick={onReset}>New</button>
      </div>

      {/* Summary stats */}
      <div className="xbrl-summary">
        <div className={`score-ring ${passRate >= 90 ? "score-good" : passRate >= 70 ? "score-mid" : "score-bad"}`}>
          <span className="score-num">{passRate}%</span>
        </div>
        <div className="xbrl-stat-grid">
          <div className="xbrl-stat">
            <span className="stat-dot dot-pass" />
            <strong>{report.summary.pass}</strong> Pass
          </div>
          <div className="xbrl-stat">
            <span className="stat-dot dot-fail" />
            <strong>{report.summary.fail}</strong> Fail
          </div>
          <div className="xbrl-stat">
            <span className="stat-dot dot-skip" />
            <strong>{report.warnings.length}</strong> Warnings
          </div>
          <div className="xbrl-stat">
            <span className="stat-dot dot-pass" />
            <strong>{report.passed ? "Yes" : "No"}</strong> Ready for XBRL
          </div>
        </div>
      </div>

      {/* Blocking failures */}
      {report.blocking_failures.length > 0 && (
        <div className="xbrl-failures">
          <h4>Blocking Issues ({report.blocking_failures.length})</h4>
          <p className="xbrl-failures-help">
            These must be fixed for a valid MCA filing. You can override with the checkbox below if this is a demo run.
          </p>
          {report.blocking_failures.map((f) => (
            <div className="xbrl-failure-item" key={f.rule_id}>
              <span className="failure-id">{f.rule_id}</span>
              <div>
                <strong>{f.name}</strong>
                <p>{f.message}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Extracted data preview */}
      <div className="xbrl-extract-preview">
        <h4>Extracted Data Preview</h4>
        <div className="extract-grid">
          <div className="extract-row">
            <span className="extract-label">Company Name</span>
            <span className="extract-value">{data?.company?.name ?? "—"}</span>
          </div>
          <div className="extract-row">
            <span className="extract-label">CIN</span>
            <span className="extract-value">{data?.company?.cin ?? "—"}</span>
          </div>
          <div className="extract-row">
            <span className="extract-label">Reporting Period</span>
            <span className="extract-value">
              {data?.reporting_period?.start_date ?? "—"} → {data?.reporting_period?.end_date ?? "—"}
            </span>
          </div>
          <div className="extract-row">
            <span className="extract-label">Total Assets (CY)</span>
            <span className="extract-value">
              {data?.balance_sheet?.current_year?.assets?.total_assets?.toLocaleString() ?? "—"}
            </span>
          </div>
          <div className="extract-row">
            <span className="extract-label">Revenue from Operations</span>
            <span className="extract-value">
              {data?.profit_loss?.current_year?.revenue_from_operations?.toLocaleString() ?? "—"}
            </span>
          </div>
          <div className="extract-row">
            <span className="extract-label">Profit for Period</span>
            <span className="extract-value">
              {data?.profit_loss?.current_year?.profit_for_period?.toLocaleString() ?? "—"}
            </span>
          </div>
          <div className="extract-row">
            <span className="extract-label">Directors</span>
            <span className="extract-value">{(data?.directors?.length ?? 0)} found</span>
          </div>
          <div className="extract-row">
            <span className="extract-label">Shareholders</span>
            <span className="extract-value">{(data?.shareholders?.length ?? 0)} found</span>
          </div>
          <div className="extract-row">
            <span className="extract-label">Auditor Firm</span>
            <span className="extract-value">{data?.auditor?.firm_name ?? "—"}</span>
          </div>
        </div>
      </div>

      {/* All rules list */}
      <div className="xbrl-rules-list">
        <h4>
          All Validation Rules
          <span className="rules-list-stats">
            <span className="stat-chip stat-chip-pass">{report.summary.pass} pass</span>
            <span className="stat-chip stat-chip-fail">{report.summary.fail} fail</span>
            {report.summary.skip > 0 && <span className="stat-chip stat-chip-skip">{report.summary.skip} skip</span>}
          </span>
        </h4>
        {report.rules.map((r) => {
          const statusLabel = r.status === "pass" ? "PASS" : r.status === "fail" ? "FAIL" : "SKIP";
          return (
            <div className={`xbrl-rule-item rule-${r.status}`} key={r.rule_id}>
              <span className={`status-badge status-${r.status}`}>{statusLabel}</span>
              <span className="rule-id">{r.rule_id}</span>
              <span className="rule-name">{r.name}</span>
              {r.status === "fail" && (
                <span className={`severity-tag sev-${r.severity}`}>{r.severity}</span>
              )}
              {r.status === "fail" && r.message && <p className="rule-msg">{r.message}</p>}
            </div>
          );
        })}
      </div>

      {/* Generate button */}
      <div className="xbrl-generate-cta">
        {!report.passed && (
          <label className="skip-validation-toggle">
            <input
              type="checkbox"
              checked={skipValidation}
              onChange={(e) => onSkipChange(e.target.checked)}
            />
            Generate XBRL anyway (demo / override blocking failures)
          </label>
        )}
        <button
          type="button"
          className="btn btn-primary btn-large"
          onClick={onGenerate}
          disabled={!report.passed && !skipValidation}
        >
          Generate XBRL XML
        </button>
      </div>
    </div>
  );
}

function BlockedView({
  report,
  onForceGenerate,
  onReset,
}: {
  report: XBRLValidationReport;
  onForceGenerate: () => void;
  onReset: () => void;
}) {
  return (
    <div className="xbrl-results">
      <div className="xbrl-header">
        <h2 className="xbrl-title">Validation Blocked Generation</h2>
        <button type="button" className="btn btn-outline btn-sm" onClick={onReset}>New</button>
      </div>
      <div className="xbrl-failures">
        <h4>{report.blocking_failures.length} blocking issue(s) — fix to produce valid MCA XBRL</h4>
        {report.blocking_failures.map((f) => (
          <div className="xbrl-failure-item" key={f.rule_id}>
            <span className="failure-id">{f.rule_id}</span>
            <div>
              <strong>{f.name}</strong>
              <p>{f.message}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="xbrl-generate-cta">
        <button type="button" className="btn btn-outline" onClick={onForceGenerate}>
          Generate Anyway (Demo / Override)
        </button>
      </div>
    </div>
  );
}

