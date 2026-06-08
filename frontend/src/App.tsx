import { useState } from "react";
import UploadZone from "./components/UploadZone";
import ValidationViewer from "./components/ValidationViewer";
import IndianXBRL from "./components/IndianXBRL";
import PdfTables from "./components/PdfTables";
import ProcessingView from "./components/ProcessingView";
import { validateDocument, type ValidationResponse } from "./api";
import "./App.css";

type AppState = "idle" | "validating" | "done" | "error";
type TabKey = "saudi" | "indian" | "tables";
type IndianStage = "idle" | "extracting" | "validated" | "generating" | "blocked" | "editing" | "error";
type TablesStage = "idle" | "extracting" | "done" | "error";
type ResultsView = "rules" | "fields";

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("saudi");
  const [state, setState] = useState<AppState>("idle");
  const [indianStage, setIndianStage] = useState<IndianStage>("idle");
  const [tablesStage, setTablesStage] = useState<TablesStage>("idle");
  const [result, setResult] = useState<ValidationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [fileSize, setFileSize] = useState<string>("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [duration, setDuration] = useState<number | undefined>(undefined);
  const [sector, setSector] = useState<string>("all");
  const [resultsView, setResultsView] = useState<ResultsView>("rules");

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

    const startTime = performance.now();
    try {
      const data = await validateDocument(file, sector);
      setDuration((performance.now() - startTime) / 1000);
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
    setDuration(undefined);
    setResultsView("rules");
  };

  const handleTabSwitch = (tab: TabKey) => {
    // Do NOT call handleReset() — each tab preserves its own state independently
    setActiveTab(tab);
  };

  const isSaudiResultsMode = activeTab === "saudi" && state === "done";

  // While the user is inside a "committed" flow on either tab — viewing Saudi
  // results, or anywhere past the upload step in the Indian flow — hide the
  // OTHER tab button so they can't accidentally switch and lose their work.
  const saudiCommitted = state === "validating" || state === "done";
  const indianCommitted = indianStage !== "idle" && indianStage !== "error";
  const tablesCommitted = tablesStage !== "idle" && tablesStage !== "error";
  const hideSaudiTab = (activeTab === "indian" && indianCommitted) || (activeTab === "tables" && tablesCommitted);
  const hideIndianTab = activeTab === "saudi" && saudiCommitted;
  const hideTablesTab = (activeTab === "saudi" && saudiCommitted) || (activeTab === "indian" && indianCommitted);

  return (
    <div className={`app ${isSaudiResultsMode ? "app-viewer-mode" : ""}`}>
      {/* Nav with tabs */}
      <nav className="nav">
        <div className="nav-brand">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 12l2 2 4-4" />
            <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z" />
          </svg>
          <span>Tawtheeq</span>
        </div>
        <div className="nav-tabs">
          {isSaudiResultsMode ? (
            <>
              <button
                type="button"
                className={`nav-tab ${resultsView === "rules" ? "nav-tab-active" : ""}`}
                onClick={() => setResultsView("rules")}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 12l2 2 4-4" />
                  <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z" />
                </svg>
                Validation Rules
                {result && <span className="nav-tab-count">{result.summary.total}</span>}
              </button>
              <button
                type="button"
                className={`nav-tab ${resultsView === "fields" ? "nav-tab-active" : ""}`}
                onClick={() => setResultsView("fields")}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <line x1="3" y1="9" x2="21" y2="9" />
                  <line x1="3" y1="15" x2="21" y2="15" />
                  <line x1="9" y1="3" x2="9" y2="21" />
                </svg>
                Extracted Fields
                {result && <span className="nav-tab-count">{result.results.length}</span>}
              </button>
            </>
          ) : (
            <>
              {!hideSaudiTab && (
                <button
                  type="button"
                  className={`nav-tab ${activeTab === "saudi" ? "nav-tab-active" : ""}`}
                  onClick={() => handleTabSwitch("saudi")}
                >
                  PDF Validation
                </button>
              )}
              {!hideTablesTab && (
                <button
                  type="button"
                  className={`nav-tab ${activeTab === "tables" ? "nav-tab-active" : ""}`}
                  onClick={() => handleTabSwitch("tables")}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <line x1="3" y1="9" x2="21" y2="9" />
                    <line x1="3" y1="15" x2="21" y2="15" />
                    <line x1="9" y1="3" x2="9" y2="21" />
                    <line x1="15" y1="3" x2="15" y2="21" />
                  </svg>
                  PDF Tables
                </button>
              )}
              {/* Indian XBRL tab hidden — set SHOW_INDIAN_TAB to true to re-enable. */}
              {false && !hideIndianTab && (
                <button
                  type="button"
                  className={`nav-tab ${activeTab === "indian" ? "nav-tab-active" : ""}`}
                  onClick={() => handleTabSwitch("indian")}
                >
                  Indian XBRL Generation
                </button>
              )}
            </>
          )}
        </div>
        {isSaudiResultsMode && (
          <button type="button" className="btn btn-outline btn-sm" onClick={handleReset}>
            New Validation
          </button>
        )}
      </nav>

      {/* SAUDI TAB */}
      {activeTab === "saudi" && (
        <>
          {state === "done" && result && pdfFile && (
            <ValidationViewer
              data={result}
              pdfFile={pdfFile}
              onReset={handleReset}
              duration={duration}
              view={resultsView}
              onPickField={() => setResultsView("rules")}
            />
          )}

          {state !== "done" && (
            <>
              <main className="main">
                {state === "idle" && (
                  <div className="landing">
                    <div className="sector-selector">
                      <label className="sector-label">Select Sector</label>
                      <div className="sector-options">
                        <button type="button" className={`sector-btn ${sector === "all" ? "sector-active" : ""}`} onClick={() => setSector("all")}>
                          All Sectors
                        </button>
                        <button type="button" className={`sector-btn ${sector === "banking_insurance" ? "sector-active" : ""}`} onClick={() => setSector("banking_insurance")}>
                          Banking &amp; Insurance
                        </button>
                        <button type="button" className={`sector-btn ${sector === "npo" ? "sector-active" : ""}`} onClick={() => setSector("npo")}>
                          NPO
                        </button>
                      </div>
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
                        <h3>23 Compliance Rules</h3>
                        <p>Validates against mandatory filing requirements for financial statements</p>
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

                {state === "validating" && (
                  <ProcessingView mode="validating" fileSummary={`${fileName} · ${fileSize}`} />
                )}

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
        </>
      )}

      {/* INDIAN XBRL TAB */}
      {activeTab === "indian" && (
        <>
          <main className="main">
            <IndianXBRL onStageChange={setIndianStage} />
          </main>
          <footer className="footer">
            <p>Tawtheeq &middot; Indian XBRL Generator (ICAI Taxonomy 2016-03-31)</p>
          </footer>
        </>
      )}

      {/* PDF TABLES TAB */}
      {activeTab === "tables" && (
        <>
          <main className="main">
            <PdfTables onStageChange={setTablesStage} />
          </main>
          <footer className="footer">
            <p>Tawtheeq &middot; Generic PDF Table Extraction</p>
          </footer>
        </>
      )}
    </div>
  );
}

export default App;
