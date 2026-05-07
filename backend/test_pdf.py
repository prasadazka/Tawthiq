"""
Test script for validating PDFs and saving results.

Usage:
    python test_pdf.py <pdf_path> [sector]
    python test_pdf.py "path/to/file.pdf"
    python test_pdf.py "path/to/file.pdf" banking_insurance

Sectors: all (default), banking_insurance, npo
Results are saved to docs/<filename>_results.json
"""

import json
import os
import sys
import time
from pathlib import Path

# Fix Windows console encoding for Arabic text
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.services.extractor import get_pdf_info
from app.services.storage import upload_pdf
from app.rules.engine import run_rules


def validate_pdf(pdf_path: str, sector: str = "all") -> dict:
    path = Path(pdf_path)
    if not path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    pdf_bytes = path.read_bytes()
    filename = path.name
    print(f"File: {filename}")
    print(f"Size: {len(pdf_bytes) / 1024:.0f} KB")
    print(f"Sector: {sector}")
    print("-" * 60)

    # Step 1: Upload to GCS
    print("[1/3] Uploading to GCS...")
    t0 = time.time()
    gcs_path = upload_pdf(pdf_bytes, filename)
    print(f"      Done ({time.time() - t0:.1f}s) -> {gcs_path}")

    # Step 2: Extract with PyMuPDF
    print("[2/3] Extracting with PyMuPDF...")
    t0 = time.time()
    doc_data = get_pdf_info(pdf_bytes)
    print(f"      Done ({time.time() - t0:.1f}s)")
    print(f"      Pages: {doc_data['page_count']}")
    print(f"      Text: {len(doc_data['full_text'])} chars")

    # Step 3: Run rules
    print("[3/3] Running rules...")
    t0 = time.time()
    results = run_rules(pdf_bytes, doc_data, sector)
    print(f"      Done ({time.time() - t0:.1f}s)")

    # Build response
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skip")
    not_applicable = sum(1 for r in results if r["status"] == "not_applicable")

    response = {
        "filename": filename,
        "gcs_path": gcs_path,
        "sector": sector,
        "extraction": {
            "page_count": doc_data["page_count"],
            "text_length": len(doc_data["full_text"]),
        },
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "not_applicable": not_applicable,
        },
        "results": results,
    }

    return response


def print_results(response: dict):
    s = response["summary"]
    print()
    print("=" * 60)
    print(f"SUMMARY: {s['passed']} passed, {s['failed']} failed, "
          f"{s['errors']} errors, {s['skipped']} skipped, "
          f"{s['not_applicable']} not applicable")
    print("=" * 60)

    for r in response["results"]:
        icons = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP",
                 "error": "ERR ", "not_applicable": "N/A "}
        icon = icons.get(r["status"], "????")
        print(f"\n[{icon}] {r['rule_id']} - {r['rule_name']}")
        print(f"       {r['details'][:200]}")
        if r.get("pages"):
            pages = r["pages"][:10]
            suffix = f"... +{len(r['pages']) - 10} more" if len(r["pages"]) > 10 else ""
            print(f"       Pages: {pages}{suffix}")


def save_results(response: dict, pdf_path: str):
    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)

    stem = Path(pdf_path).stem
    out_path = docs_dir / f"{stem}_results.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(response, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    pdf_path = sys.argv[1]
    sector = sys.argv[2] if len(sys.argv) > 2 else "all"

    response = validate_pdf(pdf_path, sector)
    save_results(response, pdf_path)
    print_results(response)
