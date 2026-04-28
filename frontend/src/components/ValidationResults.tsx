import type { ValidationResponse } from "../api";

interface Props {
  data: ValidationResponse;
  onReset: () => void;
}

export default function ValidationResults({ data, onReset }: Props) {
  const { summary, results, filename, extraction } = data;
  const passRate = summary.total > 0 ? Math.round((summary.passed / summary.total) * 100) : 0;

  return (
    <div className="results">
      {/* Score overview */}
      <div className="score-card">
        <div className="score-left">
          <div className={`score-ring ${passRate >= 80 ? "score-good" : passRate >= 50 ? "score-mid" : "score-bad"}`}>
            <span className="score-num">{passRate}%</span>
          </div>
          <div>
            <h2 className="score-title">Validation Complete</h2>
            <p className="score-file">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              {filename}
              <span className="score-pages">{extraction.page_count} pages</span>
            </p>
          </div>
        </div>
        <button type="button" className="btn btn-outline btn-sm" onClick={onReset}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
          New
        </button>
      </div>

      {/* Stats */}
      <div className="stats">
        <div className="stat">
          <span className="stat-dot dot-pass" />
          <span className="stat-num">{summary.passed}</span>
          <span className="stat-label">Passed</span>
        </div>
        <div className="stat">
          <span className="stat-dot dot-fail" />
          <span className="stat-num">{summary.failed}</span>
          <span className="stat-label">Failed</span>
        </div>
        <div className="stat">
          <span className="stat-dot dot-skip" />
          <span className="stat-num">{summary.skipped}</span>
          <span className="stat-label">Skipped</span>
        </div>
        <div className="stat">
          <span className="stat-dot dot-error" />
          <span className="stat-num">{summary.errors}</span>
          <span className="stat-label">Errors</span>
        </div>
      </div>

      {/* Rule rows */}
      <div className="rules-section">
        <h3 className="rules-heading">Rule Details</h3>
        <div className="rules-list">
          {results.map((r) => (
            <div key={r.rule_id} className={`rule-row rule-${r.status}`}>
              <div className={`rule-indicator ind-${r.status}`} />
              <div className="rule-body">
                <div className="rule-top">
                  <span className="rule-id">{r.rule_id}</span>
                  <span className="rule-name">{r.rule_name}</span>
                  <span className={`rule-badge badge-${r.status}`}>
                    {r.status}
                  </span>
                </div>
                <p className="rule-details">{r.details}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
