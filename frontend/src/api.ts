const API_BASE = import.meta.env.PROD
  ? "https://tawthiq-backend-273154047321.us-central1.run.app"
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
  status: "pass" | "fail" | "skip" | "error";
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
