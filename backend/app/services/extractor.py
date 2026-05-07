import os
import logging
import fitz  # PyMuPDF
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, Part
from groq import Groq

load_dotenv()

logger = logging.getLogger(__name__)

_vertex_initialized = False
_groq_client: Groq | None = None


# ---------------------------------------------------------------------------
# PyMuPDF utilities (replaces Document AI)
# ---------------------------------------------------------------------------

def get_pdf_info(pdf_bytes: bytes) -> dict:
    """Extract page count and full text using PyMuPDF. Replaces Document AI."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = ""
    page_count = len(doc)
    for page in doc:
        full_text += page.get_text("text") + "\n"
    doc.close()
    return {
        "full_text": full_text,
        "page_count": page_count,
    }


def resolve_evidence_locations(pdf_bytes: bytes, locations_data: list[dict]) -> list[dict]:
    """Resolve evidence quotes to bounding boxes for all locations.

    Args:
        pdf_bytes: The raw PDF bytes.
        locations_data: List of {"page": int, "bounding_boxes": [], "evidence_quotes": [...]}

    Returns:
        List of {"page": int, "bounding_boxes": [...]} in frontend-compatible format.
        Falls back to empty bounding_boxes (full-page highlight) if no quotes found.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    results = []

    for loc in locations_data:
        page_num = loc["page"]
        quotes = loc.get("evidence_quotes", [])
        all_boxes = []

        if page_num >= 1 and page_num <= len(doc):
            page = doc[page_num - 1]  # fitz uses 0-indexed
            page_rect = page.rect

            for quote in quotes:
                if not quote or not isinstance(quote, str) or not quote.strip():
                    continue
                text_instances = page.search_for(quote.strip())
                for rect in text_instances:
                    x0 = max(0.0, min(1.0, rect.x0 / page_rect.width))
                    y0 = max(0.0, min(1.0, rect.y0 / page_rect.height))
                    x1 = max(0.0, min(1.0, rect.x1 / page_rect.width))
                    y1 = max(0.0, min(1.0, rect.y1 / page_rect.height))
                    all_boxes.append({
                        "vertices": [
                            {"x": x0, "y": y0},
                            {"x": x1, "y": y0},
                            {"x": x1, "y": y1},
                            {"x": x0, "y": y1},
                        ]
                    })

        results.append({"page": page_num, "bounding_boxes": all_boxes})

    doc.close()
    return results


# ---------------------------------------------------------------------------
# LLM query functions
# ---------------------------------------------------------------------------

def _init_vertex():
    global _vertex_initialized
    if _vertex_initialized:
        return
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    vertexai.init(project=project_id, location=location)
    _vertex_initialized = True


def query_with_gemini(pdf_bytes: bytes, prompt: str) -> str:
    """Send PDF directly to Gemini via Vertex AI for analysis."""
    _init_vertex()
    model = GenerativeModel("gemini-2.5-flash")

    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    temp = float(os.getenv("GEMINI_TEMPERATURE", "0.0"))
    config = GenerationConfig(temperature=temp)
    response = model.generate_content([pdf_part, prompt], generation_config=config)
    return response.text


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable is not set")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def query_with_groq(prompt: str, document_text: str) -> str:
    """Send extracted document text to Groq LLM for analysis."""
    client = _get_groq_client()
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a financial document validator. You will be given extracted text from a PDF document and must validate it according to the given rules. Always respond in the exact JSON format requested.",
            },
            {
                "role": "user",
                "content": f"DOCUMENT TEXT:\n{document_text}\n\n---\n\n{prompt}",
            },
        ],
        temperature=float(os.getenv("GROQ_TEMPERATURE", "0.1")),
        max_tokens=1024,
    )
    return response.choices[0].message.content


def query_llm(prompt: str, document_text: str, pdf_bytes: bytes | None = None) -> str:
    """Unified LLM query — routes to Groq or Vertex AI based on LLM_PROVIDER env var.

    Set LLM_PROVIDER=gemini (default) to use Vertex AI Gemini with raw PDF bytes.
    Set LLM_PROVIDER=groq to use Groq with extracted text.
    """
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "gemini":
        if pdf_bytes is None:
            raise ValueError("pdf_bytes is required when LLM_PROVIDER=gemini")
        return query_with_gemini(pdf_bytes, prompt)

    return query_with_groq(prompt, document_text)
