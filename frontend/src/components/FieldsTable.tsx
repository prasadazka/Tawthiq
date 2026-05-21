import { useMemo, useState } from "react";
import type { RuleResult } from "../api";

interface Props {
  results: RuleResult[];
  onPageClick: (ruleId: string, page: number) => void;
}

type Filter = "all" | "found" | "missing";

const STATUS_LABEL: Record<string, string> = {
  pass: "Found",
  fail: "Missing",
  skip: "Skipped",
  error: "Error",
  not_applicable: "N/A",
};

/* Split details "<evidence> | <ai explanation>" into a primary value
   and an optional secondary line. */
function parseEvidence(details: string): { value: string; explanation: string } {
  if (!details) return { value: "—", explanation: "" };
  const parts = details.split("|").map((s) => s.trim());
  if (parts.length >= 2) {
    return { value: parts[0] || "—", explanation: parts.slice(1).join(" | ").trim() };
  }
  return { value: parts[0] || "—", explanation: "" };
}

export default function FieldsTable({ results, onPageClick }: Props) {
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

  const counts = useMemo(() => {
    return {
      all: results.length,
      found: results.filter((r) => r.status === "pass").length,
      missing: results.filter((r) => r.status === "fail").length,
    };
  }, [results]);

  return (
    <div className="fields-tab">
      <div className="fields-toolbar">
        <div className="fields-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search fields…"
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
          <span role="columnheader">Field</span>
          <span role="columnheader">Extracted value</span>
          <span role="columnheader">Pages</span>
        </div>
        {filtered.length === 0 && (
          <div className="fields-empty">No matching fields</div>
        )}
        {filtered.map((r) => {
          const { value, explanation } = parseEvidence(r.details);
          const hasPages = r.locations && r.locations.length > 0;
          return (
            <div key={r.rule_id} className={`fields-row fields-status-${r.status}`} role="row">
              <div className="fields-cell fields-cell-field" role="cell">
                <span className={`fields-status-dot dot-${r.status}`} />
                <div className="fields-cell-field-text">
                  <span className="fields-cell-name">{r.rule_name}</span>
                  <span className="fields-cell-id">{r.rule_id} · {STATUS_LABEL[r.status] || r.status}</span>
                </div>
              </div>
              <div className="fields-cell fields-cell-value" role="cell">
                <span className="fields-cell-value-primary">{value}</span>
                {explanation && <span className="fields-cell-value-secondary">{explanation}</span>}
              </div>
              <div className="fields-cell fields-cell-pages" role="cell">
                {hasPages ? (
                  r.locations.map((l, idx) => (
                    <button
                      key={`${l.page}-${idx}`}
                      type="button"
                      className="fields-page-tag"
                      onClick={() => onPageClick(r.rule_id, l.page)}
                    >
                      p.{l.page}
                    </button>
                  ))
                ) : (
                  <span className="fields-page-empty">—</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
