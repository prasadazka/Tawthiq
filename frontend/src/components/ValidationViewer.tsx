import { useState, useEffect, useMemo } from "react";
import RulesPanel from "./RulesPanel";
import FieldsTable from "./FieldsTable";
import PdfViewer from "./PdfViewer";
import type { ValidationResponse, RuleLocation } from "../api";

interface Props {
  data: ValidationResponse;
  pdfFile: File;
  onReset: () => void;
  duration?: number;
}

type Tab = "rules" | "fields";

export default function ValidationViewer({ data, pdfFile, onReset, duration }: Props) {
  const [selectedRule, setSelectedRule] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [pdfUrl, setPdfUrl] = useState("");
  const [tab, setTab] = useState<Tab>("rules");

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
  };

  const selectedLocations: RuleLocation[] = useMemo(() => {
    if (!selectedRule) return [];
    const rule = data.results.find((r) => r.rule_id === selectedRule);
    return rule?.locations || [];
  }, [selectedRule, data.results]);

  if (!pdfUrl) return null;

  return (
    <div className="viewer">
      <div className="viewer-sidebar">
        <div className="viewer-tabbar">
          <button
            type="button"
            className={`viewer-tab ${tab === "rules" ? "active" : ""}`}
            onClick={() => setTab("rules")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 12l2 2 4-4" />
              <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z" />
            </svg>
            <span>Rules</span>
            <span className="viewer-tab-count">{data.summary.total}</span>
          </button>
          <button
            type="button"
            className={`viewer-tab ${tab === "fields" ? "active" : ""}`}
            onClick={() => setTab("fields")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <line x1="3" y1="9" x2="21" y2="9" />
              <line x1="3" y1="15" x2="21" y2="15" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </svg>
            <span>Extracted fields</span>
            <span className="viewer-tab-count">{data.results.length}</span>
          </button>
        </div>

        {tab === "rules" ? (
          <RulesPanel
            data={data}
            selectedRule={selectedRule}
            onRuleClick={handleRuleClick}
            onPageClick={handlePageClick}
            onReset={onReset}
            duration={duration}
          />
        ) : (
          <FieldsTable results={data.results} onPageClick={handlePageClick} />
        )}
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
