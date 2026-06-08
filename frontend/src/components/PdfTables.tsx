import { useMemo, useState } from "react";
import UploadZone from "./UploadZone";
import ProcessingView from "./ProcessingView";
import { extractPdfTables, type PdfTablesResponse, type PdfTable } from "../api";

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
        <ResultsView data={result} onReset={handleReset} />
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

// ─── Results ────────────────────────────────────────────────────────────────

function ResultsView({ data, onReset }: { data: PdfTablesResponse; onReset: () => void }) {
  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [openIds, setOpenIds] = useState<Set<string>>(() => {
    // Open first three by default
    const ids = new Set<string>();
    data.tables.slice(0, 3).forEach((t) => ids.add(t.table_id));
    return ids;
  });

  const categories = useMemo(() => {
    const set = new Set<string>();
    data.tables.forEach((t) => t.category && set.add(t.category));
    return Array.from(set).sort();
  }, [data.tables]);

  const filteredTables = useMemo(() => {
    return data.tables.filter((t) => {
      if (!t.found || !t.rows || t.rows.length === 0) return false;
      if (categoryFilter !== "all" && t.category !== categoryFilter) return false;
      if (query) {
        const q = query.toLowerCase();
        const title = (t.title_as_printed || t.target_title || "").toLowerCase();
        if (!title.includes(q) && !t.table_id.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [data.tables, categoryFilter, query]);

  const toggle = (id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => setOpenIds(new Set(filteredTables.map((t) => t.table_id)));
  const collapseAll = () => setOpenIds(new Set());

  return (
    <div className="pdf-tables-results">
      <div className="pdf-tables-header">
        <div className="pdf-tables-titles">
          <h2>Extracted Tables</h2>
          <p>
            {data.filename} · {data.page_count} pages ·{" "}
            <strong>{data.table_count_extracted}</strong> of{" "}
            <strong>{data.table_count_inventory}</strong> tables ·{" "}
            <strong>{data.total_rows}</strong> rows · {data.total_seconds}s
          </p>
        </div>
        <button type="button" className="btn btn-outline btn-sm" onClick={onReset}>
          New PDF
        </button>
      </div>

      <div className="pdf-tables-toolbar">
        <div className="fields-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search tables by title…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="fields-filters">
          <button
            type="button"
            className={`fields-filter ${categoryFilter === "all" ? "active" : ""}`}
            onClick={() => setCategoryFilter("all")}
          >
            All <span>{data.tables.filter((t) => t.found && t.rows?.length).length}</span>
          </button>
          {categories.map((cat) => {
            const count = data.tables.filter((t) => t.category === cat && t.found && t.rows?.length).length;
            if (count === 0) return null;
            return (
              <button
                key={cat}
                type="button"
                className={`fields-filter ${categoryFilter === cat ? "active" : ""}`}
                onClick={() => setCategoryFilter(cat)}
              >
                {cat.replace(/_/g, " ")} <span>{count}</span>
              </button>
            );
          })}
        </div>
        <div className="pdf-tables-actions">
          <button type="button" className="dual-slot-action" onClick={expandAll}>
            Expand all
          </button>
          <button type="button" className="dual-slot-action" onClick={collapseAll}>
            Collapse all
          </button>
        </div>
      </div>

      <div className="pdf-tables-list">
        {filteredTables.length === 0 && (
          <div className="fields-empty">No tables match your filter</div>
        )}
        {filteredTables.map((t) => (
          <TableCard
            key={t.table_id}
            table={t}
            open={openIds.has(t.table_id)}
            onToggle={() => toggle(t.table_id)}
          />
        ))}
      </div>
    </div>
  );
}

function formatCell(value: string | number | null): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (Number.isInteger(value) && Math.abs(value) >= 1000) {
      return value.toLocaleString();
    }
    return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(value);
}

function isNumeric(value: string | number | null): boolean {
  return typeof value === "number";
}

function TableCard({ table, open, onToggle }: { table: PdfTable; open: boolean; onToggle: () => void }) {
  const title = table.title_as_printed || table.target_title || table.table_id;
  const rowCount = table.rows?.length ?? 0;
  const colCount = table.columns?.length ?? 0;

  return (
    <div className={`pdf-table-card ${open ? "open" : ""}`}>
      <button type="button" className="pdf-table-card-header" onClick={onToggle}>
        <span className="pdf-table-card-chevron">{open ? "▾" : "▸"}</span>
        <div className="pdf-table-card-titles">
          <span className="pdf-table-card-title">{title}</span>
          <span className="pdf-table-card-meta">
            {table.category && <span className="pdf-table-tag">{table.category.replace(/_/g, " ")}</span>}
            {table.page && <span>Page {table.page}</span>}
            <span>{rowCount} rows × {colCount} cols</span>
            {table.currency && <span>{table.currency}</span>}
          </span>
        </div>
      </button>
      {open && (
        <div className="pdf-table-card-body">
          {rowCount > 0 ? (
            <div className="pdf-table-scroll">
              <table className="pdf-table">
                <thead>
                  <tr>
                    {table.columns.map((col, i) => (
                      <th key={i}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row, ri) => (
                    <tr key={ri}>
                      {table.columns.map((col, ci) => {
                        const v = row[col];
                        const num = isNumeric(v);
                        return (
                          <td key={ci} className={num ? "num" : ""}>
                            {formatCell(v ?? null)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="pdf-table-empty">No rows extracted</div>
          )}
          {table.notes && <div className="pdf-table-notes">Note: {table.notes}</div>}
        </div>
      )}
    </div>
  );
}
