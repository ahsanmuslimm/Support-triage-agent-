"""Extract text from attachments for RAG indexing."""

from dataclasses import dataclass
from enum import Enum

import structlog

log = structlog.get_logger()


class ExtractionStatus(str, Enum):
    """Text extraction status."""

    SUCCESS = "success"
    UNSUPPORTED = "unsupported"
    ERROR = "error"
    EMPTY = "empty"


@dataclass
class ExtractionResult:
    """Result of text extraction."""

    status: ExtractionStatus
    """Extraction status."""

    text: str = ""
    """Extracted text."""

    char_count: int = 0
    """Number of characters extracted."""

    pages: int = 0
    """Number of pages (for PDFs)."""

    error: str | None = None
    """Error message if extraction failed."""


class TextExtractor:
    """Extract text from PDF, images, and documents."""

    async def extract_pdf_text(self, file_path: str) -> ExtractionResult:
        """Extract text from PDF using pdfplumber.

        Args:
            file_path: Path to PDF file.

        Returns:
            ExtractionResult: Extracted text and metadata.
        """
        try:
            import pdfplumber

            log.info("pdf_extraction_start", file=file_path)

            with pdfplumber.open(file_path) as pdf:
                text_parts = []
                for _page_num, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)

                full_text = "\n\n---PAGE BREAK---\n\n".join(text_parts)

                result = ExtractionResult(
                    status=ExtractionStatus.SUCCESS,
                    text=full_text,
                    char_count=len(full_text),
                    pages=len(pdf.pages),
                )
                log.info(
                    "pdf_extraction_complete",
                    file=file_path,
                    pages=len(pdf.pages),
                    chars=len(full_text),
                )
                return result

        except Exception as e:
            log.error("pdf_extraction_error", error=str(e), file=file_path)
            return ExtractionResult(
                status=ExtractionStatus.ERROR,
                error=str(e),
            )

    async def extract_image_text(self, file_path: str) -> ExtractionResult:
        """Extract text from image using Tesseract OCR.

        Args:
            file_path: Path to image file (jpg, png, tiff).

        Returns:
            ExtractionResult: Extracted text.
        """
        try:
            import pytesseract
            from PIL import Image

            log.info("ocr_extraction_start", file=file_path)

            # Open image
            img = Image.open(file_path)

            # Extract text
            text = pytesseract.image_to_string(img)

            result = ExtractionResult(
                status=ExtractionStatus.SUCCESS,
                text=text.strip(),
                char_count=len(text),
                pages=1,
            )
            log.info("ocr_extraction_complete", file=file_path, chars=len(text))
            return result

        except Exception as e:
            log.error("ocr_extraction_error", error=str(e), file=file_path)
            return ExtractionResult(
                status=ExtractionStatus.ERROR,
                error=str(e),
            )

    async def extract_docx_text(self, file_path: str) -> ExtractionResult:
        """Extract text from DOCX document.

        Args:
            file_path: Path to DOCX file.

        Returns:
            ExtractionResult: Extracted text.
        """
        try:
            from docx import Document

            log.info("docx_extraction_start", file=file_path)

            doc = Document(file_path)
            text_parts = []

            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            # Extract table text
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text for cell in row.cells)
                    if row_text.strip():
                        text_parts.append(row_text)

            full_text = "\n".join(text_parts)

            result = ExtractionResult(
                status=ExtractionStatus.SUCCESS,
                text=full_text,
                char_count=len(full_text),
                pages=1,
            )
            log.info("docx_extraction_complete", file=file_path, chars=len(full_text))
            return result

        except Exception as e:
            log.error("docx_extraction_error", error=str(e), file=file_path)
            return ExtractionResult(
                status=ExtractionStatus.ERROR,
                error=str(e),
            )

    async def extract_text(self, file_path: str, filename: str) -> ExtractionResult:
        """Extract text from any supported format.

        Args:
            file_path: Path to file.
            filename: Filename with extension.

        Returns:
            ExtractionResult: Extracted text.
        """
        ext = filename.lower()[filename.rfind(""):] if "." in filename else ""

        # Route to appropriate extractor
        if ext == ".pdf":
            return await self.extract_pdf_text(file_path)
        elif ext in (".jpg", ".jpeg", ".png", ".tiff", ".gif"):
            return await self.extract_image_text(file_path)
        elif ext in (".docx", ".doc"):
            return await self.extract_docx_text(file_path)
        else:
            return ExtractionResult(
                status=ExtractionStatus.UNSUPPORTED,
                error=f"Unsupported format: {ext}",
            )
