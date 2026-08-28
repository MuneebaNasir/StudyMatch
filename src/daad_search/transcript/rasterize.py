import fitz  # PyMuPDF

MAX_TRANSCRIPT_PAGES = 5


def file_to_page_images(file_bytes: bytes, content_type: str) -> list[bytes]:
    """Turn an uploaded transcript (PDF or image) into a list of PNG page images.

    Vision-capable LLMs and the local VLM fallback both consume plain images,
    so a PDF's pages are rasterized here rather than sent as PDF bytes -- this
    keeps extraction uniform across every provider in the fallback chain
    instead of relying on provider-specific PDF support. Capped at
    MAX_TRANSCRIPT_PAGES to keep the request payload and local VLM inference
    time bounded.
    """
    if content_type == "application/pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        return [page.get_pixmap().tobytes("png") for page in doc[:MAX_TRANSCRIPT_PAGES]]
    return [file_bytes]
