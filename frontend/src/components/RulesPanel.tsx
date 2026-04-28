import type { RuleResult, ValidationResponse } from "../api";

interface Props {
  data: ValidationResponse;
  selectedRule: string | null;
  onRuleClick: (ruleId: string) => void;
  onReset: () => void;
}

export default function RulesPanel({
  data,
  selectedRule,
  onRuleClick,
  onReset,
}: Props) {
  const { summary, results, filename, extraction } = data;
  const passRate =
    summary.total > 0
      ? Math.round((summary.passed / summary.total) * 100)
      : 0;

  return (
    <div className="panel">
      {/* Score header */}
      <div className="panel-header">
        <div className="panel-score-row">
          <div
            className={`score-ring score-ring-sm ${
              passRate >= 80
                ? "score-good"
                : passRate >= 50
                ? "score-mid"
                : "score-bad"
            }`}
          >
            <span className="score-num">{passRate}%</span>
          </div>
          <div className="panel-file-info">
            <h3 className="panel-title">Validation Complete</h3>
            <p className="panel-filename">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              {filename}
              <span className="panel-pages">
                {extraction.page_count} pages
              </span>
            </p>
          </div>
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={onReset}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
            New
          </button>
        </div>

        {/* Stats row */}
        <div className="panel-stats">
          <div className="panel-stat">
            <span className="stat-dot dot-pass" />
            <span className="panel-stat-num">{summary.passed}</span>
            <span className="panel-stat-label">Pass</span>
          </div>
          <div className="panel-stat">
            <span className="stat-dot dot-fail" />
            <span className="panel-stat-num">{summary.failed}</span>
            <span className="panel-stat-label">Fail</span>
          </div>
          <div className="panel-stat">
            <span className="stat-dot dot-skip" />
            <span className="panel-stat-num">{summary.skipped}</span>
            <span className="panel-stat-label">Skip</span>
          </div>
          <div className="panel-stat">
            <span className="stat-dot dot-error" />
            <span className="panel-stat-num">{summary.errors}</span>
            <span className="panel-stat-label">Error</span>
          </div>
        </div>
      </div>

      {/* Rules list */}
      <div className="panel-rules">
        <h4 className="panel-section-title">Rules</h4>
        {results.map((r: RuleResult) => {
          const hasLocations = r.locations && r.locations.length > 0;
          const isSelected = selectedRule === r.rule_id;

          return (
            <div
              key={r.rule_id}
              className={`panel-rule ${isSelected ? "panel-rule-selected" : ""} ${
                hasLocations ? "panel-rule-clickable" : ""
              }`}
              onClick={() => onRuleClick(r.rule_id)}
            >
              <div className={`rule-indicator ind-${r.status}`} />
              <div className="panel-rule-body">
                <div className="panel-rule-top">
                  <span className="rule-id">{r.rule_id}</span>
                  <span className="panel-rule-name">{r.rule_name}</span>
                  <span className={`rule-badge badge-${r.status}`}>
                    {r.status}
                  </span>
                </div>
                <p className="panel-rule-details">{r.details}</p>
                {hasLocations && (
                  <div className="panel-rule-pages">
                    <svg
                      width="10"
                      height="10"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                    {r.locations.map((l) => `p.${l.page}`).join(", ")}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
