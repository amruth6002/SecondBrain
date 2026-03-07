"""PDF text extraction service using PyMuPDF."""

import fitz  # PyMuPDF
import io


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text content from a PDF file.

    Args:
        pdf_bytes: Raw PDF file bytes

    Returns:
        Extracted text as a single string
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip():
            pages_text.append(f"[Page {page_num + 1}]\n{text.strip()}")

    doc.close()
    return "\n\n".join(pages_text)
