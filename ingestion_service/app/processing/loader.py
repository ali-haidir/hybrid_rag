from typing import List, Dict
from pypdf import PdfReader
from fastapi import UploadFile


class DocumentLoader:
    @staticmethod
    def load_pages(file: UploadFile) -> List[Dict]:
        """
        Load document content and return a list of:
        { "page": int, "text": str }

        Currently supports PDF only.
        """
        if not file.filename.lower().endswith(".pdf"):
            raise ValueError("Unsupported file type. Only PDF is supported.")

        # Make sure we're at the beginning of the file
        file.file.seek(0)

        reader = PdfReader(file.file)

        pages: List[Dict] = []
        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            page_text = page_text.strip()
            if not page_text:
                continue

            pages.append(
                {
                    "page": idx + 1,  # 1-based page index
                    "text": page_text,
                }
            )

        if not pages:
            raise ValueError("No readable text found in PDF.")

        return pages

    @staticmethod
    def load(file: UploadFile) -> str:
        """
        Backwards-compatible API:
        - Still returns a single big string
        - Internally uses load_pages()
        """
        pages = DocumentLoader.load_pages(file)
        return "\n\n".join(p["text"] for p in pages)
