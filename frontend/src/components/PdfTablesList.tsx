import { useMemo, useState } from "react";
import type { PdfTable } from "../api";

interface Props {
  tables: PdfTable[];
  totalRows?: number;
  filename?: string;
  pageCount?: number;
  elapsedSeconds?: number;
  onReset?: () => void;
  showHeader?: boolean;
  /** When set, shows a warning banner: some tables timed out and the result is partial. */
  partial?: boolean;
  timedOutCount?: number;
  onRetry?: () => void;
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

export default function PdfTablesList({
  tables,
  totalRows,
  filename,
  pageCount,
  elapsedSeconds,
  onReset,
  showHeader = true,
  partial = false,
  timedOutCount = 0,
  onRetry,
}: Props) {
  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [openIds, setOpenIds] = useState<Set<string>>(() => {
    const ids = new Set<string>();
    tables.slice(0, 3).forEach((t) => ids.add(t.table_id));
    return ids;
  });

  const categories = useMemo(() => {
    const set = new Set<string>();
    tables.forEach((t) => t.category && set.add(t.category));
    return Array.from(set).sort();
  }, [tables]);

  const filteredTables = useMemo(() => {
    return tables.filter((t) => {
      if (!t.found || !t.rows || t.rows.length === 0) return false;
      if (categoryFilter !== "all" && t.category !== categoryFilter) return false;
      if (query) {
        const q = query.toLowerCase();
        const title = (t.title_as_printed || t.target_title || "").toLowerCase();
        if (!title.includes(q) && !t.table_id.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [tables, categoryFilter, query]);

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

  const extracted = tables.filter((t) => t.found && t.rows?.length).length;

  return (
    <div className="pdf-tables-results">
      {showHeader && (
        <div className="pdf-tables-header">
          <div className="pdf-tables-titles">
            <h2>Extracted Tables</h2>
            <p>
              {filename ? `${filename} · ` : ""}
              {pageCount ? `${pageCount} pages · ` : ""}
              <strong>{extracted}</strong> tables
              {typeof totalRows === "number" ? <> · <strong>{totalRows}</strong> rows</> : null}
              {typeof elapsedSeconds === "number" ? ` · ${elapsedSeconds}s` : ""}
            </p>
          </div>
          {onReset && (
            <button type="button" className="btn btn-outline btn-sm" onClick={onReset}>
              New PDF
            </button>
          )}
        </div>
      )}

      {partial && (
        <div className="pdf-tables-partial">
          <div className="pdf-tables-partial-icon">!</div>
          <div className="pdf-tables-partial-body">
            <strong>Partial result.</strong>{" "}
            {timedOutCount > 0
              ? `${timedOutCount} table${timedOutCount === 1 ? "" : "s"} timed out before finishing. `
              : "Some tables timed out before finishing. "}
            The tables below are everything that completed. Retry to attempt the rest.
          </div>
          {onRetry && (
            <button type="button" className="btn btn-outline btn-sm" onClick={onRetry}>
              Retry extraction
            </button>
          )}
        </div>
      )}

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
            All <span>{extracted}</span>
          </button>
          {categories.map((cat) => {
            const count = tables.filter((t) => t.category === cat && t.found && t.rows?.length).length;
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
