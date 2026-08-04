from pathlib import Path

from daad_search.scraping.detail_parser import parse_detail_sections

FIXTURE = Path(__file__).parent / "fixtures" / "detail_page_10396.html"


def test_parse_detail_sections_extracts_known_labels():
    html = FIXTURE.read_text(encoding="utf-8")
    sections = parse_detail_sections(html)

    assert "description" in sections
    assert "Plastics Technologies in Additive Manufacturing" in sections["description"]

    assert "admission_requirements" in sections
    assert "three-year German Bachelor" in sections["admission_requirements"]
    assert "GRE Revised General Test" in sections["admission_requirements"]

    assert sections["german_language"] == "No minimum language level required"
    assert "B2" in sections["english_language"]

    assert sections["degree"] == "Master of Science"


def test_parse_detail_sections_ignores_unmapped_labels():
    html = (
        "<dl><dt class='c-description-list__content'>Some Unmapped Label</dt>"
        "<dd class='c-description-list__content'>value</dd></dl>"
    )
    assert parse_detail_sections(html) == {}
