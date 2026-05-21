import { useMemo, useState } from "react";
import type { RuleResult } from "../api";

interface Props {
  results: RuleResult[];
  /** Unused in this view — kept for backwards compatibility with ValidationViewer. */
  onPageClick?: (ruleId: string, page: number) => void;
}

type Filter = "all" | "found" | "missing";

const STATUS_LABEL: Record<string, string> = {
  pass: "Found",
  fail: "Missing",
  skip: "Skipped",
  error: "Error",
  not_applicable: "Not Applicable",
};

/* Build the "extracted value" display for a rule row.
   Priority:
   1. evidence_quotes[] — these are verbatim strings the AI pulled from the PDF.
   2. The "evidence" half of details ("<evidence> | <explanation>").
   3. Whole details string.
   Returns the verbatim quotes (if any) plus a secondary line with the rule's
   own narrative finding. */
function buildExtractedDisplay(r: { details: string; evidence_quotes?: string[] }):
  { quotes: string[]; summary: string } {
  const quotes = (r.evidence_quotes || []).map((q) => q.trim()).filter(Boolean);

  const trimmed = (r.details || "").trim();
  let summary = trimmed;
  const idx = trimmed.indexOf("|");
  if (idx !== -1) {
    const right = trimmed.slice(idx + 1).trim();
    if (right) summary = right;
  }

  return { quotes, summary };
}

export default function FieldsTable({ results }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    return results.filter((r) => {
      if (filter === "found" && r.status !== "pass") return false;
      if (filter === "missing" && r.status === "pass") return false;
      if (filter === "missing" && (r.status === "skip" || r.status === "not_applicable")) return false;
      if (query) {
        const q = query.toLowerCase();
        const hay = `${r.rule_id} ${r.rule_name} ${r.details}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [results, filter, query]);

  const counts = useMemo(
    () => ({
      all: results.length,
      found: results.filter((r) => r.status === "pass").length,
      missing: results.filter((r) => r.status === "fail").length,
    }),
    [results]
  );

  const coverage = counts.all > 0 ? Math.round((counts.found / counts.all) * 100) : 0;

  return (
    <div className="fields-tab">
      <header className="fields-header">
        <div className="fields-header-titles">
          <h2>Extracted Fields</h2>
          <p>Every value the AI pulled from the document, in one place. No PDF needed.</p>
        </div>
        <div className="fields-header-coverage">
          <span className="fields-coverage-num">{coverage}%</span>
          <span className="fields-coverage-label">
            {counts.found} of {counts.all} fields extracted
          </span>
        </div>
      </header>

      <div className="fields-toolbar">
        <div className="fields-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search fields or values…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="fields-filters">
          <button
            type="button"
            className={`fields-filter ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            All <span>{counts.all}</span>
          </button>
          <button
            type="button"
            className={`fields-filter ${filter === "found" ? "active" : ""}`}
            onClick={() => setFilter("found")}
          >
            Found <span>{counts.found}</span>
          </button>
          <button
            type="button"
            className={`fields-filter ${filter === "missing" ? "active" : ""}`}
            onClick={() => setFilter("missing")}
          >
            Missing <span>{counts.missing}</span>
          </button>
        </div>
      </div>

      <div className="fields-table" role="table">
        <div className="fields-row fields-row-head" role="row">
          <span role="columnheader">#</span>
          <span role="columnheader">Field</span>
          <span role="columnheader">Extracted value</span>
          <span role="columnheader">Status</span>
        </div>
        {filtered.length === 0 && (
          <div className="fields-empty">No matching fields</div>
        )}
        {filtered.map((r, idx) => {
          const { quotes, summary } = buildExtractedDisplay(r);
          const hasQuotes = quotes.length > 0;
          return (
            <div key={r.rule_id} className={`fields-row fields-status-${r.status}`} role="row">
              <div className="fields-cell fields-cell-index" role="cell">
                {idx + 1}
              </div>
              <div className="fields-cell fields-cell-field" role="cell">
                <span className={`fields-status-dot dot-${r.status}`} />
                <div className="fields-cell-field-text">
                  <span className="fields-cell-name">{r.rule_name}</span>
                  <span className="fields-cell-id">{r.rule_id}</span>
                </div>
              </div>
              <div className="fields-cell fields-cell-value" role="cell">
                {hasQuotes ? (
                  <ul className="fields-quotes">
                    {quotes.map((q, i) => (
                      <li key={i} className="fields-quote">
                        <span className="fields-quote-mark">“</span>
                        {q}
                        <span className="fields-quote-mark">”</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="fields-cell-value-primary fields-cell-value-empty">
                    {r.status === "pass" ? "Found — no verbatim quote captured" : "Not extracted"}
                  </span>
                )}
                {summary && (
                  <span className="fields-cell-value-secondary">{summary}</span>
                )}
              </div>
              <div className="fields-cell fields-cell-status" role="cell">
                <span className={`fields-status-pill pill-${r.status}`}>
                  {STATUS_LABEL[r.status] || r.status}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
