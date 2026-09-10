import io

import fitz
import pytest
from PIL import Image

from daad_search.transcript.rasterize import TranscriptPageTooLargeError, file_to_page_images


def _make_pdf_bytes(num_pages: int, page_width: float = 595, page_height: float = 842) -> bytes:
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page(width=page_width, height=page_height)
    return doc.tobytes()


def _make_image_bytes(fmt: str, size=(4, 4)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


def test_file_to_page_images_rasterizes_each_pdf_page():
    pdf_bytes = _make_pdf_bytes(2)
    images = file_to_page_images(pdf_bytes, "application/pdf")
    assert len(images) == 2
    assert all(img.startswith(b"\x89PNG") for img in images)


def test_file_to_page_images_caps_at_max_pages():
    pdf_bytes = _make_pdf_bytes(8)
    images = file_to_page_images(pdf_bytes, "application/pdf")
    assert len(images) == 5


def test_file_to_page_images_normalizes_a_png_upload_to_png():
    png_bytes = _make_image_bytes("PNG")
    images = file_to_page_images(png_bytes, "image/png")
    assert len(images) == 1
    assert images[0].startswith(b"\x89PNG")


def test_file_to_page_images_normalizes_a_jpeg_upload_to_png():
    jpeg_bytes = _make_image_bytes("JPEG")
    assert jpeg_bytes.startswith(b"\xff\xd8\xff")  # sanity: really is a JPEG going in

    images = file_to_page_images(jpeg_bytes, "image/jpeg")

    assert len(images) == 1
    # Must come out as a real PNG so build_image_message's hardcoded
    # data:image/png;base64 URI is actually accurate.
    assert images[0].startswith(b"\x89PNG")
    Image.open(io.BytesIO(images[0]))  # round-trips as a valid image


def test_file_to_page_images_raises_on_bytes_that_are_not_a_real_image():
    with pytest.raises(Exception):
        file_to_page_images(b"not-an-image-at-all", "image/png")


def test_file_to_page_images_rejects_a_pdf_page_with_an_oversized_mediabox():
    # A page whose declared dimensions would rasterize, at RASTERIZE_DPI, to
    # well beyond MAX_PAGE_AREA_PX -- e.g. a crafted MediaBox intended to
    # force a huge pixmap allocation.
    huge_points_side = 10_000  # within the PDF spec's page-size limit, but enormous for a transcript
    pdf_bytes = _make_pdf_bytes(1, page_width=huge_points_side, page_height=huge_points_side)

    with pytest.raises(TranscriptPageTooLargeError):
        file_to_page_images(pdf_bytes, "application/pdf")


def test_file_to_page_images_accepts_a_normal_sized_pdf_page():
    pdf_bytes = _make_pdf_bytes(1, page_width=595, page_height=842)  # A4
    images = file_to_page_images(pdf_bytes, "application/pdf")
    assert len(images) == 1
