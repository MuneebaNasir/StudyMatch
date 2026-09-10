import io

import fitz  # PyMuPDF
from PIL import Image

MAX_TRANSCRIPT_PAGES = 5

# Fixed render resolution -- deliberately NOT left to get_pixmap()'s default
# (which scales with the PDF's own point-space page size, effectively
# uncontrolled). 150 DPI is plenty for transcript text legibility.
RASTERIZE_DPI = 150

# Ceiling on a rendered page's pixel area at RASTERIZE_DPI. A0 at 150 DPI is
# roughly 4963x7016px (~34.8M px); this cap sits comfortably above any
# realistic transcript page (A4/Letter) while still blocking a crafted PDF
# whose MediaBox declares an enormous page purely to force get_pixmap() into
# allocating a huge (~600MB+) pixmap.
MAX_PAGE_AREA_PX = 40_000_000


class TranscriptPageTooLargeError(Exception):
    """Raised when a PDF page's declared dimensions would rasterize to an
    unreasonably large pixmap. Caught by extractor.py's existing
    corrupt/unparseable-transcript handling, same as any other rasterization
    failure."""


def file_to_page_images(file_bytes: bytes, content_type: str) -> list[bytes]:
    """Turn an uploaded transcript (PDF or image) into a list of PNG page images.

    Vision-capable LLMs and the local VLM fallback both consume plain images,
    so a PDF's pages are rasterized here rather than sent as PDF bytes -- this
    keeps extraction uniform across every provider in the fallback chain
    instead of relying on provider-specific PDF support. Capped at
    MAX_TRANSCRIPT_PAGES to keep the request payload and local VLM inference
    time bounded.

    Non-PDF input is normalized to real PNG bytes via Pillow rather than
    passed through untouched: this keeps the bytes handed to
    build_image_message() consistent with the `data:image/png;base64,...`
    URI it hardcodes (a JPEG upload previously stayed a JPEG but got mislabeled
    as PNG), and PIL.Image.open() fails loudly on bytes that aren't a real
    image regardless of what the caller claimed the content-type was.
    """
    if content_type == "application/pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        images = []
        scale = RASTERIZE_DPI / 72  # PDF page rect is in points (1/72 inch)
        for page in doc[:MAX_TRANSCRIPT_PAGES]:
            rect = page.rect
            page_area_px = (rect.width * scale) * (rect.height * scale)
            if page_area_px > MAX_PAGE_AREA_PX:
                raise TranscriptPageTooLargeError(
                    f"Transcript page too large to rasterize safely: "
                    f"{rect.width:.0f}x{rect.height:.0f}pt at {RASTERIZE_DPI} DPI"
                )
            images.append(page.get_pixmap(dpi=RASTERIZE_DPI).tobytes("png"))
        return images

    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return [buffer.getvalue()]
