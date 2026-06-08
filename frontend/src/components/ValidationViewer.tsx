import { useState, useEffect, useMemo } from "react";
import RulesPanel from "./RulesPanel";
import FieldsTable from "./FieldsTable";
import PdfTablesList from "./PdfTablesList";
import PdfViewer from "./PdfViewer";
import type { ValidationResponse, RuleLocation } from "../api";

interface Props {
  data: ValidationResponse;
  pdfFile: File;
  onReset: () => void;
  duration?: number;
  view?: "rules" | "fields" | "tables";
  onPickField?: () => void;
}

export default function ValidationViewer({ data, pdfFile, onReset, duration, view = "rules", onPickField }: Props) {
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
    return (
      <div className="viewer viewer-fields">
        <PdfTablesList
          tables={data.tables?.items || []}
          totalRows={data.tables?.total_rows}
          filename={data.filename}
          pageCount={data.extraction.page_count}
          showHeader
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
