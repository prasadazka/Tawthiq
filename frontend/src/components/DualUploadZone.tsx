import { useCallback, useState, useRef } from "react";

type SlotKind = "pdf" | "excel";

interface SlotProps {
  kind: SlotKind;
  step: number;
  file: File | null;
  onFile: (file: File) => void;
  onClear: () => void;
  disabled?: boolean;
}

const SLOT_META: Record<
  SlotKind,
  {
    title: string;
    subtitle: string;
    hint: string;
    accept: string;
    badge: string;
    extPattern: RegExp;
    mimePattern: RegExp;
  }
> = {
  pdf: {
    title: "Audited Financials",
    subtitle: "Signed audit-report PDF",
    hint: "Narratives, signatures, auditor identity",
    accept: "application/pdf,.pdf",
    badge: "PDF",
    extPattern: /\.pdf$/i,
    mimePattern: /pdf/i,
  },
  excel: {
    title: "CA Working File",
    subtitle: "Source workbook (.xlsx)",
    hint: "Notes, ratios, PPE schedule, RPT",
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

function SlotIcon({ kind }: { kind: SlotKind }) {
  if (kind === "pdf") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="9" y1="13" x2="15" y2="13" />
        <line x1="9" y1="17" x2="15" y2="17" />
      </svg>
    );
  }
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="3" y1="15" x2="21" y2="15" />
      <line x1="9" y1="3" x2="9" y2="21" />
      <line x1="15" y1="3" x2="15" y2="21" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function Slot({ kind, step, file, onFile, onClear, disabled }: SlotProps) {
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

  const openPicker = () => !disabled && inputRef.current?.click();

  const filled = !!file;

  return (
    <div
      className={`dual-slot ${dragOver ? "drag-over" : ""} ${disabled ? "disabled" : ""} ${filled ? "filled" : ""}`}
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

      <div className="dual-slot-header">
        <div className="dual-slot-step">
          {filled ? <CheckIcon /> : <span>{step}</span>}
        </div>
        <div className="dual-slot-titles">
          <div className="dual-slot-title-row">
            <h4>{meta.title}</h4>
            <span className="dual-slot-badge">{meta.badge}</span>
          </div>
          <p className="dual-slot-subtitle">{meta.subtitle}</p>
        </div>
        <div className="dual-slot-icon">
          <SlotIcon kind={kind} />
        </div>
      </div>

      <div className="dual-slot-hint">{meta.hint}</div>

      {filled ? (
        <div className="dual-slot-file">
          <div className="dual-slot-file-icon">
            <SlotIcon kind={kind} />
          </div>
          <div className="dual-slot-file-meta">
            <span className="dual-slot-file-name" title={file.name}>{file.name}</span>
            <span className="dual-slot-file-size">{formatSize(file.size)}</span>
          </div>
          <div className="dual-slot-file-actions">
            <button type="button" className="dual-slot-action" onClick={openPicker}>Replace</button>
            <button type="button" className="dual-slot-action dual-slot-action-danger" onClick={onClear}>Remove</button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="dual-slot-drop"
          onClick={openPicker}
          disabled={disabled}
        >
          <span className="dual-slot-drop-primary">
            Drop file here or <span className="dual-slot-drop-link">browse</span>
          </span>
          <span className="dual-slot-drop-secondary">Max 50 MB</span>
        </button>
      )}

      {error && <p className="dual-slot-error">{error}</p>}
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

  const count = (pdf ? 1 : 0) + (excel ? 1 : 0);
  const ready = count === 2 && !disabled;
  const cta = !pdf && !excel
    ? "Upload both files to continue"
    : !pdf
    ? "Add the PDF to continue"
    : !excel
    ? "Add the Excel to continue"
    : "Extract & Validate";

  return (
    <div className="dual-upload">
      <div className="dual-upload-progress">
        <span className="dual-upload-progress-label">Required documents</span>
        <span className="dual-upload-progress-count">
          <strong>{count}</strong> of 2 uploaded
        </span>
        <div className={`dual-upload-progress-bar progress-${count}`}>
          <div className="dual-upload-progress-fill" />
        </div>
      </div>

      <div className="dual-upload-slots">
        <Slot
          kind="pdf"
          step={1}
          file={pdf}
          onFile={setPdf}
          onClear={() => setPdf(null)}
          disabled={disabled}
        />
        <Slot
          kind="excel"
          step={2}
          file={excel}
          onFile={setExcel}
          onClear={() => setExcel(null)}
          disabled={disabled}
        />
      </div>

      <div className="dual-upload-footer">
        <button
          type="button"
          className="btn btn-primary btn-large dual-upload-cta"
          disabled={!ready}
          onClick={() => ready && onFilesReady(pdf!, excel!)}
        >
          {cta}
        </button>
        <p className="dual-upload-note">
          Tawthiq merges both sources — Excel supplies precise schedules and ratios, the PDF supplies signatures, narratives and the audit opinion.
        </p>
      </div>
    </div>
  );
}
