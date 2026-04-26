from typing import List

import fitz


def extract_pages_from_pdf(file_bytes: bytes) -> List[str]:
    pages: List[str] = []

    with fitz.open(stream=file_bytes, filetype="pdf") as document:
        for page in document:
            text = page.get_text("text").strip()
            pages.append(text)

    return pages
