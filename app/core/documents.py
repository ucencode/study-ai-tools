"""PDF rendering and PPTX conversion.

pypdfium2 renders pages without needing poppler installed; LibreOffice is only
required for PPTX input and is optional.
"""

import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import pypdfium2

LIBREOFFICE_BINARIES = ("libreoffice", "soffice")

# LibreOffice on a cold profile is slow, and a corrupt file can make it hang forever.
CONVERT_TIMEOUT = 300


class DocumentError(RuntimeError):
    """Conversion or rendering failed."""


def libreoffice_binary() -> str | None:
    for name in LIBREOFFICE_BINARIES:
        if path := shutil.which(name):
            return path
    return None


def libreoffice_available() -> bool:
    return libreoffice_binary() is not None


def pptx_to_pdf(source: Path, out_dir: Path) -> Path:
    """Convert a .pptx to PDF, returning the new file's path."""
    binary = libreoffice_binary()
    if binary is None:
        raise DocumentError(
            "LibreOffice is not installed, so .pptx input cannot be converted. "
            "Install it, or export the deck to PDF yourself."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [binary, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(source)],
            capture_output=True,
            text=True,
            timeout=CONVERT_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise DocumentError(f"LibreOffice timed out after {CONVERT_TIMEOUT}s converting {source.name}") from e

    if result.returncode != 0:
        raise DocumentError(f"LibreOffice failed on {source.name}: {result.stderr.strip()}")

    # It names the output after the input stem, not after anything we pass.
    converted = out_dir / f"{source.stem}.pdf"
    if not converted.exists():
        raise DocumentError(f"LibreOffice reported success but produced no PDF for {source.name}")
    return converted


def page_count(pdf: Path) -> int:
    document = pypdfium2.PdfDocument(str(pdf))
    try:
        return len(document)
    finally:
        document.close()


def render_page(pdf: Path, index: int, dpi: int = 200) -> bytes:
    """Render one page to PNG bytes.

    One page at a time on purpose: a 200-page deck at 300 dpi is gigabytes if you
    materialize it. Reopening the document each call costs a few milliseconds against
    an OCR round trip measured in seconds, and it keeps every PDFium handle confined
    to the calling thread — which matters because callers run this in a worker thread.
    """
    document = pypdfium2.PdfDocument(str(pdf))
    try:
        image = document[index].render(scale=dpi / 72).to_pil()
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        document.close()
