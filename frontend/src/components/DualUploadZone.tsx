import { useCallback, useState, useRef } from "react";

type SlotKind = "pdf" | "excel";

interface SlotProps {
  kind: SlotKind;
  file: File | null;
  onFile: (file: File) => void;
  disabled?: boolean;
}

const SLOT_META: Record<
  SlotKind,
  { title: string; subtitle: string; accept: string; badge: string; extPattern: RegExp; mimePattern: RegExp }
> = {
  pdf: {
    title: "Audited Financials",
    subtitle: "PDF — signed audit report",
    accept: "application/pdf,.pdf",
    badge: "PDF",
    extPattern: /\.pdf$/i,
    mimePattern: /pdf/i,
  },
  excel: {
    title: "CA Working File",
    subtitle: "Excel — Notes, Ratios, PPE, RPT",
    accept:
      ".xlsx,.xls,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel",
    badge: "XLSX",
    extPattern: /\.(xlsx|xls|xlsm)$/i,
    mimePattern: /(sheet|excel|spreadsheet)/i,
  },
};

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function Slot({ kind, file, onFile, disabled }: SlotProps) {
  const meta = SLOT_META[kind];
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (f: File) => {
      setError(null);
      const validExt = meta.extPattern.test(f.name);
      const validMime = !f.type || meta.mimePattern.test(f.type);
      if (!validExt || !validMime) {
        setError(`Only ${meta.badge} files accepted`);
        return;
      }
      if (f.size > 50 * 1024 * 1024) {
        setError("File size must be under 50 MB");
        return;
      }
      if (f.size === 0) {
        setError("File is empty");
        return;
      }
      onFile(f);
    },
    [onFile, meta]
  );

  const filled = !!file;

  return (
    <div
      className={`upload-zone dual-slot ${dragOver ? "drag-over" : ""} ${disabled ? "disabled" : ""} ${filled ? "filled" : ""}`}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (disabled) return;
        const f = e.dataTransfer.files[0];
        if (f) handleFile(f);
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onClick={() => !disabled && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept={meta.accept}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
          e.target.value = "";
        }}
        hidden
      />
      <div className="upload-icon-wrap">
        {kind === "pdf" ? (
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        ) : (
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="9" y1="3" x2="9" y2="21" />
            <line x1="15" y1="3" x2="15" y2="21" />
            <line x1="3" y1="9" x2="21" y2="9" />
            <line x1="3" y1="15" x2="21" y2="15" />
          </svg>
        )}
      </div>
      <p className="upload-title">{meta.title}</p>
      <p className="upload-sub">{meta.subtitle}</p>
      {filled ? (
        <div className="upload-filled">
          <strong>{file.name}</strong>
          <span>
            {formatSize(file.size)} &middot; <span className="upload-link">replace</span>
          </span>
        </div>
      ) : (
        <p className="upload-sub">
          Drop here or <span className="upload-link">browse</span>
        </p>
      )}
      <div className="upload-meta">
        <span className="upload-badge">{meta.badge}</span>
        <span className="upload-limit">Max 50 MB</span>
      </div>
      {error && <p className="upload-error">{error}</p>}
    </div>
  );
}

interface Props {
  onFilesReady: (pdf: File, excel: File) => void;
  disabled?: boolean;
}

export default function DualUploadZone({ onFilesReady, disabled }: Props) {
  const [pdf, setPdf] = useState<File | null>(null);
  const [excel, setExcel] = useState<File | null>(null);

  const ready = !!pdf && !!excel && !disabled;
  const cta = !pdf && !excel
    ? "Upload both files to continue"
    : !pdf
    ? "Add PDF to continue"
    : !excel
    ? "Add Excel to continue"
    : "Extract & Validate";

  return (
    <div className="upload-dual">
      <div className="upload-dual-slots">
        <Slot kind="pdf" file={pdf} onFile={setPdf} disabled={disabled} />
        <Slot kind="excel" file={excel} onFile={setExcel} disabled={disabled} />
      </div>
      <button
        type="button"
        className="btn btn-primary btn-large upload-cta"
        disabled={!ready}
        onClick={() => ready && onFilesReady(pdf!, excel!)}
      >
        {cta}
      </button>
    </div>
  );
}
