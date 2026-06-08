import { useState } from "react";
import UploadZone from "./UploadZone";
import ProcessingView from "./ProcessingView";
import PdfTablesList from "./PdfTablesList";
import { extractPdfTables, type PdfTablesResponse } from "../api";

type Stage = "idle" | "extracting" | "done" | "error";

interface Props {
  onStageChange?: (stage: Stage) => void;
}

export default function PdfTables({ onStageChange }: Props = {}) {
  const [stage, _setStage] = useState<Stage>("idle");
  const setStage = (s: Stage) => {
    _setStage(s);
    onStageChange?.(s);
  };
  const [fileName, setFileName] = useState("");
  const [fileSize, setFileSize] = useState("");
  const [result, setResult] = useState<PdfTablesResponse | null>(null);
  const [error, setError] = useState("");

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFile = async (file: File) => {
    setFileName(file.name);
    setFileSize(formatSize(file.size));
    setError("");
    setStage("extracting");
    try {
      const data = await extractPdfTables(file);
      setResult(data);
      setStage("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed");
      setStage("error");
    }
  };

  const handleReset = () => {
    setStage("idle");
    setResult(null);
    setError("");
    setFileName("");
    setFileSize("");
  };

  return (
    <div className="pdf-tables">
      {stage === "idle" && (
        <div className="landing">
          <div className="hero">
            <h1>PDF Table Extraction</h1>
            <p className="hero-sub">
              Upload any PDF — financial statements, technical reports, audit
              reports. Tawthiq finds every table inside, extracts the structured
              data, and shows it side by side.
            </p>
          </div>
          <UploadZone onFileSelected={handleFile} />
          <div className="features">
            <div className="feature">
              <h3>Inventory + Extract</h3>
              <p>Two-pass extraction: lists every table on every page, then pulls each table's full structure in parallel.</p>
            </div>
            <div className="feature">
              <h3>Works on any PDF</h3>
              <p>No company-specific templates. Same pipeline handles Saudi audits, Indian XBRL filings, technical schedules.</p>
            </div>
            <div className="feature">
              <h3>Year-aware columns</h3>
              <p>Comparatives (31 Dec 2025 vs 31 Dec 2024) come back as separate columns. Parentheses → negatives.</p>
            </div>
          </div>
        </div>
      )}

      {stage === "extracting" && (
        <ProcessingView mode="pdf_tables" fileSummary={`${fileName} · ${fileSize}`} />
      )}

      {stage === "done" && result && (
        <PdfTablesList
          tables={result.tables}
          totalRows={result.total_rows}
          filename={result.filename}
          pageCount={result.page_count}
          elapsedSeconds={result.total_seconds}
          onReset={handleReset}
        />
      )}

      {stage === "error" && (
        <div className="error-card">
          <h3>Extraction Failed</h3>
          <p className="error-msg">{error}</p>
          <button type="button" className="btn btn-primary" onClick={handleReset}>
            Try Again
          </button>
        </div>
      )}
    </div>
  );
}
