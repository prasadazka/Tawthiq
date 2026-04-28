import os
from datetime import datetime
from google.cloud import storage
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def upload_pdf(pdf_bytes: bytes, filename: str) -> str:
    """Upload PDF to GCS. Returns the gs:// path."""
    bucket_name = os.getenv("GCS_BUCKET_NAME", "tawthiq-docs")
    client = _get_client()
    bucket = client.bucket(bucket_name)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    blob_name = f"uploads/{timestamp}_{filename}"

    blob = bucket.blob(blob_name)
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")

    return f"gs://{bucket_name}/{blob_name}"
