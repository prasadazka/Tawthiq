import { useEffect, useMemo, useRef, useState } from "react";

interface Step {
  id: string;
  label: string;
  detail: string;
  /** Approximate seconds this step typically takes (used for UX pacing only). */
  etaSeconds: number;
}

const EXTRACT_STEPS: Step[] = [
  { id: "upload", label: "Files received", detail: "Validating signatures and size", etaSeconds: 1 },
  { id: "pdf-parse", label: "Reading the PDF", detail: "Indexing pages with PyMuPDF", etaSeconds: 2 },
  { id: "xlsx-parse", label: "Reading the Excel workbook", detail: "Converting 12 sheets to structured tables", etaSeconds: 2 },
  { id: "gemini", label: "AI extracting financial data", detail: "Running PDF and Excel through Gemini in parallel", etaSeconds: 55 },
  { id: "merge", label: "Merging extractions", detail: "Excel wins for numbers, PDF wins for narratives", etaSeconds: 2 },
  { id: "validate", label: "Validating 33 MCA rules", detail: "Balance sheet equation, CIN, DIN, audit dates, signatures", etaSeconds: 3 },
];

const GENERATE_STEPS: Step[] = [
  { id: "load-template", label: "Loading XBRL template", detail: "ICAI in-gaap + in-ca taxonomy, 491 unique tags", etaSeconds: 1 },
  { id: "fill", label: "Filling 1,496 facts", detail: "Mapping extracted JSON onto contexts and units", etaSeconds: 3 },
  { id: "compose", label: "Computing composite subtotals", detail: "Shareholders' funds, total assets, cash flow rollups", etaSeconds: 2 },
  { id: "encode", label: "Encoding XBRL XML", detail: "UTF-16 encoding, MCA-portal compatible", etaSeconds: 2 },
];

const VALIDATE_STEPS: Step[] = [
  { id: "upload", label: "File received", detail: "Verifying PDF signature and size", etaSeconds: 1 },
  { id: "parse", label: "Reading the PDF", detail: "Extracting text and tables with PyMuPDF", etaSeconds: 3 },
  { id: "ai", label: "AI rule evaluation", detail: "Gemini reads each section and answers 23 compliance checks", etaSeconds: 55 },
  { id: "summary", label: "Compiling validation report", detail: "Aggregating pass/fail with evidence locations", etaSeconds: 2 },
];

const PDF_TABLES_STEPS: Step[] = [
  { id: "upload", label: "File received", detail: "Verifying PDF signature and size", etaSeconds: 1 },
  { id: "parse", label: "Reading the PDF", detail: "Indexing pages with PyMuPDF", etaSeconds: 2 },
  { id: "inventory", label: "Inventorying tables in the PDF", detail: "Gemini enumerates every table on every page", etaSeconds: 25 },
  { id: "extract", label: "Extracting each table", detail: "Running Gemini in parallel — one call per table for structured rows", etaSeconds: 45 },
  { id: "assemble", label: "Assembling results", detail: "Sorting by page, normalising columns, attaching categories", etaSeconds: 2 },
];

const TIPS_XBRL = [
  "Gemini reads the full PDF natively — no OCR needed.",
  "The Excel workbook provides Note 7 PPE per-asset-class breakdown.",
  "Sheet \"Sch III Ratios\" supplies the 14 mandatory analytical ratios.",
  "Related party transactions come from the Add Notes sheet.",
  "Trade payable aging buckets are extracted from Sheet2.",
  "Shareholder reconciliation comes from Notes 2.1 and 2.2.",
  "The generated XBRL uses the same template the CA submitted last year.",
  "Validation runs balance-sheet equation: Assets = Liabilities + Equity.",
];

const TIPS_VALIDATE = [
  "Both Arabic and English statements are supported.",
  "Each rule cites the page and quotes the evidence it found.",
  "Rules cover signatures, dates, totals, disclosures and required statements.",
  "Pass/fail is auditable — every result links back to a PDF location.",
  "Sector-specific rules apply for Banking, Insurance and NPO documents.",
];

const TIPS_PDF_TABLES = [
  "Inventory first, extract second — keeps the model focused per table.",
  "Tables rotated 90° (landscape on portrait page) are read in their natural order.",
  "Parentheses are negatives: \"(1,234)\" becomes -1234.",
  "Multi-line column headers are joined into a single space-separated string.",
  "When a year column says \"31 December 2025\", it's kept as its own column.",
  "Narrative paragraphs that look like tables are intentionally skipped.",
  "Same pipeline works for Saudi audits, Indian filings, and any other PDF.",
];

interface Props {
  mode: "extracting" | "generating" | "validating" | "pdf_tables";
  fileSummary?: string;
}

const MODE_CONFIG: Record<Props["mode"], { steps: Step[]; tips: string[]; note: string }> = {
  extracting: {
    steps: EXTRACT_STEPS,
    tips: TIPS_XBRL,
    note: "Extracting & validating — typically 60–90 seconds",
  },
  generating: {
    steps: GENERATE_STEPS,
    tips: TIPS_XBRL,
    note: "Generating XBRL — typically 5–10 seconds",
  },
  validating: {
    steps: VALIDATE_STEPS,
    tips: TIPS_VALIDATE,
    note: "Reading PDF and running rules — typically 60–90 seconds",
  },
  pdf_tables: {
    steps: PDF_TABLES_STEPS,
    tips: TIPS_PDF_TABLES,
    note: "Inventory + per-table extraction — typically 60–90 seconds",
  },
};

function pad(n: number) {
  return n.toString().padStart(2, "0");
}

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${pad(m)}:${pad(s)}`;
}

export default function ProcessingView({ mode, fileSummary }: Props) {
  const { steps, tips, note } = MODE_CONFIG[mode];

  const [elapsed, setElapsed] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const [tipIndex, setTipIndex] = useState(0);
  const startRef = useRef(Date.now());
  const totalEta = useMemo(() => steps.reduce((a, s) => a + s.etaSeconds, 0), [steps]);

  /* Tick elapsed every second */
  useEffect(() => {
    const id = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  /* Advance step pointer based on cumulative ETA. The longest step (AI extraction)
     dominates and is sticky — we never "skip past" it, the parent unmounts us. */
  useEffect(() => {
    let cumulative = 0;
    for (let i = 0; i < steps.length; i++) {
      cumulative += steps[i].etaSeconds;
      if (elapsed < cumulative) {
        setActiveIndex(i);
        return;
      }
    }
    setActiveIndex(steps.length - 1);
  }, [elapsed, steps]);

  /* Rotate tip every 6 seconds */
  useEffect(() => {
    const id = window.setInterval(() => {
      setTipIndex((i) => (i + 1) % tips.length);
    }, 6000);
    return () => window.clearInterval(id);
  }, [tips.length]);

  const remaining = Math.max(0, totalEta - elapsed);
  const overrun = elapsed > totalEta;
  const progressPct = Math.min(95, Math.round((elapsed / totalEta) * 100));

  return (
    <div className="processing">
      {fileSummary && (
        <div className="processing-files">
          <div className="processing-files-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <div className="processing-files-text">
            <span className="processing-files-label">Files received</span>
            <span className="processing-files-detail">{fileSummary}</span>
          </div>
        </div>
      )}

      <div className="processing-summary">
        <div className="processing-summary-block">
          <span className="processing-summary-label">Elapsed</span>
          <span className="processing-summary-value">{formatElapsed(elapsed)}</span>
        </div>
        <div className="processing-summary-bar">
          <div className="processing-summary-bar-track">
            <div
              className={`processing-summary-bar-fill progress-${Math.floor(progressPct / 10) * 10}`}
            />
          </div>
          <span className="processing-summary-bar-note">
            {overrun ? "Taking a little longer than usual — still working" : note}
          </span>
        </div>
        <div className="processing-summary-block processing-summary-block-right">
          <span className="processing-summary-label">{overrun ? "Status" : "Est. remaining"}</span>
          {overrun ? (
            <span className="processing-summary-value processing-status-working">Working…</span>
          ) : (
            <span className="processing-summary-value">~{formatElapsed(remaining)}</span>
          )}
        </div>
      </div>

      <ol className="processing-timeline">
        {steps.map((step, idx) => {
          const status = idx < activeIndex ? "done" : idx === activeIndex ? "active" : "pending";
          return (
            <li key={step.id} className={`processing-step processing-step-${status}`}>
              <div className="processing-step-marker">
                {status === "done" ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : status === "active" ? (
                  <span className="processing-step-spinner" />
                ) : (
                  <span className="processing-step-dot" />
                )}
              </div>
              <div className="processing-step-body">
                <div className="processing-step-label-row">
                  <span className="processing-step-label">{step.label}</span>
                  {status === "active" && <span className="processing-step-tag">In progress</span>}
                  {status === "done" && <span className="processing-step-tag processing-step-tag-done">Done</span>}
                </div>
                <span className="processing-step-detail">{step.detail}</span>
                {status === "active" && (
                  <div className="processing-step-progress">
                    <div className="processing-step-progress-fill" />
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      <div className="processing-tip" key={tipIndex}>
        <div className="processing-tip-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 18h6" />
            <path d="M10 22h4" />
            <path d="M12 2a7 7 0 0 0-4 12.7c.7.5 1 1.3 1 2.1V18h6v-1.2c0-.8.3-1.6 1-2.1A7 7 0 0 0 12 2z" />
          </svg>
        </div>
        <span>{tips[tipIndex]}</span>
      </div>
    </div>
  );
}
