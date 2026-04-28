import { useState } from "react";
import UploadZone from "./components/UploadZone";
import ValidationResults from "./components/ValidationResults";
import { validateDocument, type ValidationResponse } from "./api";
import "./App.css";

type AppState = "idle" | "validating" | "done" | "error";

function App() {
  const [state, setState] = useState<AppState>("idle");
  const [result, setResult] = useState<ValidationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");

  const handleFile = async (file: File) => {
    setState("validating");
    setFileName(file.name);
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
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>Tawthiq</h1>
        <p className="app-subtitle">Financial Document Validation</p>
      </header>

      <main className="app-main">
        {state === "idle" && <UploadZone onFileSelected={handleFile} />}

        {state === "validating" && (
          <div className="loading">
            <div className="spinner" />
            <p className="loading-text">Validating <strong>{fileName}</strong></p>
            <p className="loading-hint">Extracting text & running rules...</p>
          </div>
        )}

        {state === "done" && result && (
          <ValidationResults data={result} onReset={handleReset} />
        )}

        {state === "error" && (
          <div className="error-box">
            <p className="error-title">Validation Failed</p>
            <p className="error-msg">{error}</p>
            <button type="button" className="btn-reset" onClick={handleReset}>Try Again</button>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
