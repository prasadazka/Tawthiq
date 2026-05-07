import { useState, useEffect, useMemo } from "react";
import RulesPanel from "./RulesPanel";
import PdfViewer from "./PdfViewer";
import type { ValidationResponse, RuleLocation } from "../api";

interface Props {
  data: ValidationResponse;
  pdfFile: File;
  onReset: () => void;
  duration?: number;
}

export default function ValidationViewer({ data, pdfFile, onReset, duration }: Props) {
  const [selectedRule, setSelectedRule] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [pdfUrl, setPdfUrl] = useState("");

  // Create object URL from File for react-pdf
  useEffect(() => {
    const url = URL.createObjectURL(pdfFile);
    setPdfUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [pdfFile]);

  // When a rule is clicked, navigate to its first location page
  const handleRuleClick = (ruleId: string) => {
    setSelectedRule(ruleId);
    const rule = data.results.find((r) => r.rule_id === ruleId);
    if (rule && rule.locations && rule.locations.length > 0) {
      setCurrentPage(rule.locations[0].page);
    }
  };

  // When an individual page tag is clicked, select the rule and jump to that page
  const handlePageClick = (ruleId: string, page: number) => {
    setSelectedRule(ruleId);
    setCurrentPage(page);
  };

  // Get all locations for the selected rule
  const selectedLocations: RuleLocation[] = useMemo(() => {
    if (!selectedRule) return [];
    const rule = data.results.find((r) => r.rule_id === selectedRule);
    return rule?.locations || [];
  }, [selectedRule, data.results]);

  if (!pdfUrl) return null;

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
