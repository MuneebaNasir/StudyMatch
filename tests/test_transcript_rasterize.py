import fitz

from daad_search.transcript.rasterize import file_to_page_images


def _make_pdf_bytes(num_pages: int) -> bytes:
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    return doc.tobytes()


def test_file_to_page_images_rasterizes_each_pdf_page():
    pdf_bytes = _make_pdf_bytes(2)
    images = file_to_page_images(pdf_bytes, "application/pdf")
    assert len(images) == 2
    assert all(img.startswith(b"\x89PNG") for img in images)


def test_file_to_page_images_caps_at_max_pages():
    pdf_bytes = _make_pdf_bytes(8)
    images = file_to_page_images(pdf_bytes, "application/pdf")
    assert len(images) == 5


def test_file_to_page_images_passes_through_a_plain_image():
    fake_png = b"\x89PNGfake-image-bytes"
    images = file_to_page_images(fake_png, "image/png")
    assert images == [fake_png]
