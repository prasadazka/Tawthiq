import { useState } from "react";
import UploadZone from "./components/UploadZone";
import ValidationViewer from "./components/ValidationViewer";
import { validateDocument, type ValidationResponse } from "./api";
import "./App.css";

type AppState = "idle" | "validating" | "done" | "error";

function App() {
  const [state, setState] = useState<AppState>("idle");
  const [result, setResult] = useState<ValidationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [fileSize, setFileSize] = useState<string>("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFile = async (file: File) => {
    setState("validating");
    setPdfFile(file);
    setFileName(file.name);
    setFileSize(formatSize(file.size));
    setError(null);

    try {
      const data = await validateDocument(file);
      setResult(data);
      setState("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
      setState("error");
    }
  };

  const handleReset = () => {
    setState("idle");
    setResult(null);
    setError(null);
    setFileName("");
    setFileSize("");
    setPdfFile(null);
  };

  return (
    <div className={`app ${state === "done" ? "app-viewer-mode" : ""}`}>
      {/* Nav */}
      <nav className="nav">
        <div className="nav-brand">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 12l2 2 4-4" />
            <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z" />
          </svg>
          <span>Tawtheeq</span>
        </div>
        {state === "done" && (
          <button type="button" className="btn btn-outline btn-sm" onClick={handleReset}>
            New Validation
          </button>
        )}
      </nav>

      {/* Results — full-width viewer */}
      {state === "done" && result && pdfFile && (
        <ValidationViewer data={result} pdfFile={pdfFile} onReset={handleReset} />
      )}

      {/* Non-results states inside main container */}
      {state !== "done" && (
        <>
          <main className="main">
            {/* Landing / Upload */}
            {state === "idle" && (
              <div className="landing">
                <div className="hero">
                  <h1>Financial Document<br />Validation Platform</h1>
                  <p className="hero-sub">
                    Upload your financial statement PDF and validate it against
                    regulatory compliance rules automatically.
                  </p>
                </div>
                <UploadZone onFileSelected={handleFile} />
                <div className="features">
                  <div className="feature">
                    <div className="feature-icon">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                    </div>
                    <h3>Document AI OCR</h3>
                    <p>Extracts text and tables from Arabic and English PDFs with high accuracy</p>
                  </div>
                  <div className="feature">
                    <div className="feature-icon">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                    </div>
                    <h3>19 Compliance Rules</h3>
                    <p>Validates against mandatory filing requirements for Saudi financial statements</p>
                  </div>
                  <div className="feature">
                    <div className="feature-icon">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
                    </div>
                    <h3>Gemini AI Analysis</h3>
                    <p>Uses Vertex AI for visual inspection and contextual validation checks</p>
                  </div>
                </div>
              </div>
            )}

            {/* Validating */}
            {state === "validating" && (
              <div className="validating-card">
                <div className="validating-file">
                  <div className="file-thumb">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                  </div>
                  <div>
                    <p className="validating-name">{fileName}</p>
                    <p className="validating-size">{fileSize}</p>
                  </div>
                </div>
                <div className="progress-section">
                  <div className="progress-bar"><div className="progress-fill" /></div>
                  <p className="progress-label">Extracting text and running validation rules...</p>
                </div>
                <div className="validating-steps">
                  <div className="step step-done">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>
                    File uploaded
                  </div>
                  <div className="step step-active">
                    <div className="step-spinner" />
                    Running Document AI OCR
                  </div>
                  <div className="step step-pending">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="10"/></svg>
                    Validating against 19 rules
                  </div>
                </div>
              </div>
            )}

            {/* Error */}
            {state === "error" && (
              <div className="error-card">
                <div className="error-icon-wrap">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                </div>
                <h3>Validation Failed</h3>
                <p className="error-msg">{error}</p>
                <button type="button" className="btn btn-primary" onClick={handleReset}>Try Again</button>
              </div>
            )}
          </main>

          <footer className="footer">
            <p>Tawtheeq &middot; Document Validation System</p>
          </footer>
        </>
      )}
    </div>
  );
}

export default App;
