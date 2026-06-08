import { useState, useEffect, useMemo } from "react";
import RulesPanel from "./RulesPanel";
import FieldsTable from "./FieldsTable";
import PdfTablesList from "./PdfTablesList";
import ProcessingView from "./ProcessingView";
import PdfViewer from "./PdfViewer";
import type {
  ValidationResponse,
  RuleLocation,
  PdfTablesResponse,
  SaudiXBRLGenerateResult,
} from "../api";

interface Props {
  data: ValidationResponse;
  pdfFile: File;
  onReset: () => void;
  duration?: number;
  view?: "rules" | "fields" | "tables" | "xbrl";
  onPickField?: () => void;
  tablesData?: PdfTablesResponse | null;
  tablesLoading?: boolean;
  tablesError?: string | null;
  tablesStartedAt?: number | null;
  // XBRL gating + actions
  xbrlReady?: boolean;
  xbrlGenerating?: boolean;
  xbrlResult?: SaudiXBRLGenerateResult | null;
  xbrlError?: string | null;
  xbrlStartedAt?: number | null;
  onGenerateXbrl?: () => void;
  onOpenTablesTab?: () => void;
}

export default function ValidationViewer({
  data, pdfFile, onReset, duration, view = "rules", onPickField,
  tablesData, tablesLoading, tablesError, tablesStartedAt,
  xbrlReady, xbrlGenerating, xbrlResult, xbrlError, xbrlStartedAt,
  onGenerateXbrl, onOpenTablesTab,
}: Props) {
  const [selectedRule, setSelectedRule] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [pdfUrl, setPdfUrl] = useState("");

  useEffect(() => {
    const url = URL.createObjectURL(pdfFile);
    setPdfUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [pdfFile]);

  const handleRuleClick = (ruleId: string) => {
    setSelectedRule(ruleId);
    const rule = data.results.find((r) => r.rule_id === ruleId);
    if (rule && rule.locations && rule.locations.length > 0) {
      setCurrentPage(rule.locations[0].page);
    }
  };

  const handlePageClick = (ruleId: string, page: number) => {
    setSelectedRule(ruleId);
    setCurrentPage(page);
    // If we're on the fields view, jump to rules view so the user sees the highlight.
    onPickField?.();
  };

  const selectedLocations: RuleLocation[] = useMemo(() => {
    if (!selectedRule) return [];
    const rule = data.results.find((r) => r.rule_id === selectedRule);
    return rule?.locations || [];
  }, [selectedRule, data.results]);

  if (!pdfUrl) return null;

  if (view === "fields") {
    return (
      <div className="viewer viewer-fields">
        <FieldsTable results={data.results} onPageClick={handlePageClick} />
      </div>
    );
  }

  if (view === "tables") {
    if (tablesLoading) {
      return (
        <div className="viewer viewer-fields">
          <ProcessingView
            mode="pdf_tables"
            fileSummary={data.filename}
            startedAt={tablesStartedAt ?? undefined}
          />
        </div>
      );
    }
    if (tablesError) {
      return (
        <div className="viewer viewer-fields">
          <div className="error-card">
            <h3>Table Extraction Failed</h3>
            <p className="error-msg">{tablesError}</p>
          </div>
        </div>
      );
    }
    if (tablesData) {
      return (
        <div className="viewer viewer-fields">
          <PdfTablesList
            tables={tablesData.tables}
            totalRows={tablesData.total_rows}
            filename={tablesData.filename}
            pageCount={tablesData.page_count}
            elapsedSeconds={tablesData.total_seconds}
            showHeader
          />
        </div>
      );
    }
    return null;
  }

  if (view === "xbrl") {
    return (
      <div className="viewer viewer-fields">
        <XbrlPanel
          ready={!!xbrlReady}
          generating={!!xbrlGenerating}
          result={xbrlResult ?? null}
          error={xbrlError ?? null}
          startedAt={xbrlStartedAt ?? undefined}
          tablesLoading={!!tablesLoading}
          tablesReady={!!tablesData}
          tablesError={tablesError ?? null}
          onGenerate={onGenerateXbrl}
          onOpenTablesTab={onOpenTablesTab}
        />
      </div>
    );
  }

  return (
    <div className="viewer">
      <div className="viewer-sidebar">
        <RulesPanel
          data={data}
          selectedRule={selectedRule}
          onRuleClick={handleRuleClick}
          onPageClick={handlePageClick}
          onReset={onReset}
          duration={duration}
        />
      </div>
      <div className="viewer-main">
        <PdfViewer
          url={pdfUrl}
          currentPage={currentPage}
          onPageChange={setCurrentPage}
          numPages={numPages}
          onNumPages={setNumPages}
          selectedLocations={selectedLocations}
        />
      </div>
    </div>
  );
}

// ─── XBRL panel ─────────────────────────────────────────────────────────────

interface XbrlPanelProps {
  ready: boolean;
  generating: boolean;
  result: SaudiXBRLGenerateResult | null;
  error: string | null;
  startedAt?: number;
  tablesLoading: boolean;
  tablesReady: boolean;
  tablesError: string | null;
  onGenerate?: () => void;
  onOpenTablesTab?: () => void;
}

function XbrlPanel({
  ready, generating, result, error, startedAt,
  tablesLoading, tablesReady, tablesError,
  onGenerate, onOpenTablesTab,
}: XbrlPanelProps) {
  if (generating) {
    return (
      <div className="xbrl-panel">
        <ProcessingView
          mode="generating"
          fileSummary="Building Saudi-IFRS XBRL"
          startedAt={startedAt}
        />
      </div>
    );
  }

  return (
    <div className="xbrl-panel">
      <header className="xbrl-panel-header">
        <h2>Saudi-IFRS XBRL</h2>
        <p>
          Combines the rule extraction (text concepts) and PDF Tables
          extraction (numeric facts) into a single XBRL instance document.
        </p>
      </header>

      <div className="xbrl-checklist">
        <ChecklistRow
          label="Validation Rules"
          status="ready"
          detail="Auto-loaded with the report"
        />
        <ChecklistRow
          label="PDF Tables"
          status={tablesReady ? "ready" : tablesLoading ? "loading" : tablesError ? "error" : "pending"}
          detail={
            tablesReady
              ? `${(tablesError ? "?" : "")}Tables extracted`
              : tablesLoading
              ? "Extracting — switch to the PDF Tables tab to watch progress"
              : tablesError
              ? tablesError
              : "Open the PDF Tables tab to start extraction"
          }
          action={
            !tablesReady && !tablesLoading && onOpenTablesTab ? (
              <button type="button" className="btn btn-outline btn-sm" onClick={onOpenTablesTab}>
                Start tables extraction
              </button>
            ) : null
          }
        />
      </div>

      {error && (
        <div className="error-card xbrl-error">
          <h3>XBRL Generation Failed</h3>
          <p className="error-msg">{error}</p>
        </div>
      )}

      {result ? (
        <div className="xbrl-result-card">
          <div className="xbrl-result-stats">
            <div className="xbrl-result-stat">
              <span className="xbrl-result-stat-num">{result.coveragePct.toFixed(1)}%</span>
              <span className="xbrl-result-stat-label">Coverage</span>
            </div>
            <div className="xbrl-result-stat">
              <span className="xbrl-result-stat-num">{result.found}</span>
              <span className="xbrl-result-stat-label">Facts emitted</span>
            </div>
            <div className="xbrl-result-stat">
              <span className="xbrl-result-stat-num">{result.elapsedSeconds.toFixed(1)}s</span>
              <span className="xbrl-result-stat-label">Build time</span>
            </div>
          </div>
          <p className="xbrl-result-note">
            XBRL XML download was triggered. Click below to regenerate or re-download.
          </p>
          <button type="button" className="btn btn-outline" onClick={onGenerate} disabled={!ready}>
            Regenerate XBRL
          </button>
        </div>
      ) : (
        <div className="xbrl-cta">
          <button
            type="button"
            className="btn btn-primary btn-large"
            onClick={onGenerate}
            disabled={!ready}
          >
            {ready ? "Generate & download XBRL" : "Waiting for Rules + PDF Tables…"}
          </button>
          <p className="xbrl-cta-help">
            Once both Rules and PDF Tables are loaded, the XBRL XML is produced
            on the server: source mapper + AI fallback + emitter. Takes ~60–90s.
          </p>
        </div>
      )}
    </div>
  );
}

function ChecklistRow({
  label, status, detail, action,
}: {
  label: string;
  status: "ready" | "loading" | "pending" | "error";
  detail: string;
  action?: React.ReactNode;
}) {
  const icon =
    status === "ready" ? "✓" : status === "loading" ? "⟳" : status === "error" ? "!" : "○";
  return (
    <div className={`xbrl-checklist-row xbrl-checklist-${status}`}>
      <span className="xbrl-checklist-icon">{icon}</span>
      <div className="xbrl-checklist-body">
        <span className="xbrl-checklist-label">{label}</span>
        <span className="xbrl-checklist-detail">{detail}</span>
      </div>
      {action}
    </div>
  );
}
