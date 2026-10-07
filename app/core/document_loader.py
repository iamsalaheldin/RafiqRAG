import io
import logging
from pathlib import Path
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from typing import Callable
from app.config.settings import DOCS_DIR, SUPPORTED_DOC_EXTENSIONS

logger = logging.getLogger(__name__)



def _extract_plain_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        raise ValueError("Text file must be UTF-8 encoded")


def _extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise ValueError(f"Could not read PDF (corrupt or password-protected): {exc}")
    return "\n\n".join(pages).strip()



_EXTRACTORS: dict[str, Callable[[bytes], str]] = {
    ".pdf":_extract_pdf_text,
    ".md":_extract_plain_text,
    ".txt":_extract_plain_text
}

def load_documents() -> list[dict]:
    """
    This function for reading every .md / .txt / .pdf file in the data/docs.
    """
    docs_dir = Path(DOCS_DIR)
    documents: list[dict] = []

    if not docs_dir.is_dir():
        logger.warning("Docs directory not found: %s", docs_dir)
        return documents
    
    for path in sorted(docs_dir.iterdir()):
        if path.suffix.lower() not in SUPPORTED_DOC_EXTENSIONS:
            continue

        try:
            text = _extract_text(path.name, path.read_bytes())
        except Exception:
            logger.exception("Skipping %s: failed to extract text", path.name)
            continue

        if not text:
            logger.warning("%s produced no extractable text", path.name)
            continue

        documents.append(
            {
                "source":path.name, 
                "text":text
            }
        )
    return documents


def _extract_text(filename: str | None, content: bytes) -> str:
    ext = Path(filename or "").suffix.lower()

    extractor = _EXTRACTORS.get(ext)

    if extractor is None:
        raise ValueError(
            f"Unsupported file type: {ext} - Supported types only: {SUPPORTED_DOC_EXTENSIONS}"
        )
    
    return extractor(content)

def extract_uploaded_document(filename: str, content:bytes) -> str:

    text = _extract_text(filename, content)

    if not text:
        raise ValueError("No extractable text found in this file")
    
    return text