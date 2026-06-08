const API_BASE = import.meta.env.PROD
  ? "https://tawthiq-backend-pn5c6ojp4a-uc.a.run.app"
  : "";

export interface BoundingBox {
  vertices: Array<{ x: number; y: number }>;
}

export interface RuleLocation {
  page: number;
  bounding_boxes: BoundingBox[];
}

export interface RuleResult {
  rule_id: string;
  rule_name: string;
  description: string;
  status: "pass" | "fail" | "skip" | "error" | "not_applicable";
  details: string;
  severity: string;
  locations: RuleLocation[];
  evidence_quotes?: string[];
}

export interface ValidationResponse {
  filename: string;
  sector: string;
  extraction: {
    method: string;
    page_count: number;
    text_length: number;
  };
  summary: {
    total: number;
    passed: number;
    failed: number;
    errors: number;
    skipped: number;
    not_applicable: number;
  };
  results: RuleResult[];
}

export async function validateDocument(
  file: File,
  sector: string = "all"
): Promise<ValidationResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("sector", sector);

  const res = await fetch(`${API_BASE}/api/validate`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }

  return res.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    const data = await res.json();
    return data.status === "ok";
  } catch {
    return false;
  }
}

// ─── Indian XBRL Generation ─────────────────────────────────────────────────

export interface XBRLValidationRule {
  rule_id: string;
  name: string;
  category: string;
  severity: "error" | "warning" | "info";
  status: "pass" | "fail" | "skip";
  message: string;
  actual?: unknown;
}

export interface XBRLValidationReport {
  passed: boolean;
  summary: { pass: number; fail: number; skip: number };
  rules: XBRLValidationRule[];
  blocking_failures: Array<{ rule_id: string; name: string; message: string }>;
  warnings: Array<{ rule_id: string; name: string; message: string }>;
}

export interface XBRLExtractResponse {
  filename: string;
  success: boolean;
  ready_for_xbrl: boolean;
  timings: {
    extract_seconds: number;
    validate_seconds: number;
    total_seconds: number;
  };
  extraction: {
    page_count: number;
    data: Record<string, unknown>;
  };
  validation: XBRLValidationReport;
}

export async function extractIndianXBRL(
  file: File,
  excel: File
): Promise<XBRLExtractResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("excel", excel);
  const res = await fetch(`${API_BASE}/api/xbrl/india/extract`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Extraction failed" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }
  return res.json();
}

export interface XBRLGenerateBlobResult {
  blob: Blob;
  filename: string;
  factCount: number;
  contextCount: number;
  validationPassed: boolean;
  warnings: number;
  elapsedSeconds: number;
}

export interface XMLValidationError {
  code: string;
  message: string;
  line: number | null;
  column?: number | null;
  element?: string | null;
}

export interface XMLEmptyFact {
  tag: string;
  context_ref: string;
  line: number;
  raw_xml: string;
}

export interface XMLValidationResponse {
  valid: boolean;
  well_formed: boolean;
  stats: { contexts: number; units: number; facts: number; empty_facts: number };
  errors: XMLValidationError[];
  warnings: XMLValidationError[];
  empty_facts: XMLEmptyFact[];
}

export async function validateXBRLXML(xml: string): Promise<XMLValidationResponse> {
  const res = await fetch(`${API_BASE}/api/xbrl/india/validate-xml`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ xml }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Validation failed" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }
  return res.json();
}

// ─── PDF Tables Extraction (generic, any PDF) ───────────────────────────────

export interface PdfTableRow {
  [columnName: string]: string | number | null;
}

export interface PdfTable {
  table_id: string;
  found: boolean;
  page: number | null;
  title_as_printed?: string | null;
  target_title?: string | null;
  category?: string | null;
  columns: string[];
  rows: PdfTableRow[];
  currency?: string | null;
  notes?: string | null;
  error?: string;
}

export interface PdfTablesResponse {
  filename: string;
  success: boolean;
  page_count: number;
  table_count_inventory: number;
  table_count_extracted: number;
  total_rows: number;
  extraction_seconds: number;
  total_seconds: number;
  tables: PdfTable[];
}

export interface SaudiXBRLMetadata {
  entity_id?: string;
  period_start_cy?: string;
  period_end_cy?: string;
  period_start_py?: string;
  period_end_py?: string;
  currency?: string;
  decimals_default?: string;
  schema_ref?: string;
}

export interface SaudiXBRLGenerateResult {
  blob: Blob;
  xml: string;       // decoded UTF-8 text — for preview
  byteSize: number;  // blob size in bytes
  filename: string;
  total: number;
  found: number;
  coveragePct: number;
  elapsedSeconds: number;
}

export async function generateSaudiXBRL(
  rulesJson: ValidationResponse,
  tablesJson: PdfTablesResponse,
  metadata: SaudiXBRLMetadata,
  filename = "saudi_xbrl.xml",
): Promise<SaudiXBRLGenerateResult> {
  const res = await fetch(`${API_BASE}/api/xbrl/saudi/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rules_json: rulesJson,
      tables_json: tablesJson,
      metadata,
      use_ai_fallback: true,
      filename,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "XBRL generation failed" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }
  const blob = await res.blob();
  const xml = await blob.text();
  return {
    blob,
    xml,
    byteSize: blob.size,
    filename,
    total: parseInt(res.headers.get("x-tawthiq-concepts-total") || "0", 10),
    found: parseInt(res.headers.get("x-tawthiq-concepts-found") || "0", 10),
    coveragePct: parseFloat(res.headers.get("x-tawthiq-coverage-pct") || "0"),
    elapsedSeconds: parseFloat(res.headers.get("x-tawthiq-elapsed-seconds") || "0"),
  };
}

export async function extractPdfTables(file: File): Promise<PdfTablesResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/pdf-tables/extract`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Extraction failed" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }
  return res.json();
}

export async function downloadEditedXBRL(xml: string, filename: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/xbrl/india/download-xml`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ xml, filename }),
  });
  if (!res.ok) throw new Error("Download failed");
  return res.blob();
}

export async function downloadExcelFromJSON(
  data: Record<string, unknown>
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${API_BASE}/api/xbrl/india/generate-excel-from-json`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Excel generation failed" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") || "";
  const m = disposition.match(/filename="([^"]+)"/);
  return { blob, filename: m ? m[1] : "tawthiq_xbrl.xlsx" };
}

export async function generateIndianXBRL(
  file: File,
  excel: File,
  skipValidation: boolean = false
): Promise<XBRLGenerateBlobResult | { validationReport: XBRLValidationReport; extractionData: Record<string, unknown> }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("excel", excel);
  formData.append("skip_validation", String(skipValidation));

  const res = await fetch(`${API_BASE}/api/xbrl/india/generate`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "XBRL generation failed" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }

  const contentType = res.headers.get("content-type") || "";

  // If validation blocked, server returns JSON instead of XML download
  if (contentType.includes("application/json")) {
    const body = await res.json();
    return {
      validationReport: body.validation,
      extractionData: body.extraction_data,
    };
  }

  // Otherwise, XBRL XML file
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") || "";
  const filenameMatch = disposition.match(/filename="([^"]+)"/);
  return {
    blob,
    filename: filenameMatch ? filenameMatch[1] : "output.xml",
    factCount: parseInt(res.headers.get("x-tawthiq-facts") || "0", 10),
    contextCount: parseInt(res.headers.get("x-tawthiq-contexts") || "0", 10),
    validationPassed: res.headers.get("x-tawthiq-validation-passed") === "true",
    warnings: parseInt(res.headers.get("x-tawthiq-warnings") || "0", 10),
    elapsedSeconds: parseFloat(res.headers.get("x-tawthiq-elapsed-seconds") || "0"),
  };
}
