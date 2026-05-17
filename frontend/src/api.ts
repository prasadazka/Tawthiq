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

export async function extractIndianXBRL(file: File): Promise<XBRLExtractResponse> {
  const formData = new FormData();
  formData.append("file", file);
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

export async function generateIndianXBRL(
  file: File,
  skipValidation: boolean = false
): Promise<XBRLGenerateBlobResult | { validationReport: XBRLValidationReport; extractionData: Record<string, unknown> }> {
  const formData = new FormData();
  formData.append("file", file);
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
