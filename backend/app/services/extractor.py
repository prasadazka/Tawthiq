import os
from google.cloud import documentai
from google.api_core.client_options import ClientOptions
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, Part

load_dotenv()

_vertex_initialized = False
DOCAI_PAGE_LIMIT = 15


def _init_vertex():
    global _vertex_initialized
    if _vertex_initialized:
        return
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    vertexai.init(project=project_id, location=location)
    _vertex_initialized = True


def _get_docai_client():
    location = os.getenv("GCP_LOCATION", "us")
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    return documentai.DocumentProcessorServiceClient(client_options=opts)


def _get_processor_name():
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "us")
    processor_id = os.getenv("GCP_PROCESSOR_ID")
    client = _get_docai_client()
    return client.processor_path(project_id, location, processor_id)


def _split_pdf(pdf_bytes: bytes, chunk_size: int = DOCAI_PAGE_LIMIT) -> list[bytes]:
    """Split PDF into chunks of chunk_size pages."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    if total_pages <= chunk_size:
        doc.close()
        return [pdf_bytes]

    chunks = []
    for start in range(0, total_pages, chunk_size):
        end = min(start + chunk_size, total_pages)
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
        chunk_bytes = new_doc.tobytes()
        new_doc.close()
        chunks.append(chunk_bytes)

    doc.close()
    return chunks


def _process_chunk(chunk_bytes: bytes, client, processor_name) -> documentai.Document:
    """Process a single PDF chunk through Document AI."""
    raw_document = documentai.RawDocument(content=chunk_bytes, mime_type="application/pdf")
    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
    result = client.process_document(request=request)
    return result.document


def extract_with_document_ai(pdf_bytes: bytes) -> dict:
    """Extract structured text, tables, and paragraph bounding boxes using Document AI OCR."""
    client = _get_docai_client()
    processor_name = _get_processor_name()

    chunks = _split_pdf(pdf_bytes)

    full_text = ""
    pages = []
    page_offset = 0

    for chunk_bytes in chunks:
        document = _process_chunk(chunk_bytes, client, processor_name)
        full_text += document.text

        for page in document.pages:
            page_text = ""
            paragraphs = []
            for paragraph in page.paragraphs:
                para_text = _get_text(paragraph.layout, document)
                page_text += para_text + "\n"
                paragraphs.append(_extract_paragraph_with_bbox(paragraph, document))

            pages.append({
                "page_number": page_offset + page.page_number,
                "text": page_text.strip(),
                "tables": _extract_tables(page, document),
                "paragraphs": paragraphs,
            })

        page_offset += len(document.pages)

    return {
        "full_text": full_text,
        "pages": pages,
        "page_count": len(pages),
    }


def _extract_paragraph_with_bbox(paragraph, document) -> dict:
    """Extract paragraph text and its bounding box coordinates."""
    text = _get_text(paragraph.layout, document)
    vertices = []
    bp = paragraph.layout.bounding_poly
    if bp and bp.normalized_vertices:
        vertices = [{"x": float(v.x), "y": float(v.y)} for v in bp.normalized_vertices]
    return {"text": text, "bounding_box": {"vertices": vertices}}


def _get_text(layout, document) -> str:
    """Extract text from a layout element using text anchors."""
    text = ""
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index) if segment.start_index else 0
        end = int(segment.end_index)
        text += document.text[start:end]
    return text.strip()


def _extract_tables(page, document) -> list[dict]:
    """Extract tables from a page."""
    tables = []
    for table in page.tables:
        header_rows = []
        for row in table.header_rows:
            cells = [_get_text(cell.layout, document) for cell in row.cells]
            header_rows.append(cells)

        body_rows = []
        for row in table.body_rows:
            cells = [_get_text(cell.layout, document) for cell in row.cells]
            body_rows.append(cells)

        tables.append({"headers": header_rows, "rows": body_rows})
    return tables


def query_with_gemini(pdf_bytes: bytes, prompt: str) -> str:
    """Send PDF directly to Gemini via Vertex AI for analysis."""
    _init_vertex()
    model = GenerativeModel("gemini-2.5-flash")

    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    response = model.generate_content([pdf_part, prompt])
    return response.text
