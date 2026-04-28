import type { ValidationResponse } from "../api";

interface Props {
  data: ValidationResponse;
  onReset: () => void;
}

const STATUS_ICON: Record<string, string> = {
  pass: "\u2705",
  fail: "\u274C",
  skip: "\u23ED",
  error: "\u26A0",
};

export default function ValidationResults({ data, onReset }: Props) {
  const { summary, results, filename, extraction } = data;

  return (
    <div className="results">
      <div className="results-header">
        <div className="results-file">
          <span className="file-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
          </span>
          <div>
            <strong>{filename}</strong>
            <span className="file-meta">{extraction.page_count} pages</span>
          </div>
        </div>
        <button className="btn-reset" onClick={onReset}>Validate Another</button>
      </div>

      <div className="summary-cards">
        <div className="card card-pass">
          <span className="card-num">{summary.passed}</span>
          <span className="card-label">Passed</span>
        </div>
        <div className="card card-fail">
          <span className="card-num">{summary.failed}</span>
          <span className="card-label">Failed</span>
        </div>
        <div className="card card-skip">
          <span className="card-num">{summary.skipped}</span>
          <span className="card-label">Skipped</span>
        </div>
        <div className="card card-error">
          <span className="card-num">{summary.errors}</span>
          <span className="card-label">Errors</span>
        </div>
      </div>

      <div className="rules-list">
        {results.map((r) => (
          <div key={r.rule_id} className={`rule-row rule-${r.status}`}>
            <span className="rule-status">{STATUS_ICON[r.status] || "?"}</span>
            <div className="rule-info">
              <div className="rule-title">
                <span className="rule-id">{r.rule_id}</span>
                {r.rule_name}
              </div>
              <p className="rule-details">{r.details}</p>
            </div>
            <span className={`severity severity-${r.severity}`}>{r.severity}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
