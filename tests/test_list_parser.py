import json
from pathlib import Path

from daad_search.scraping.list_parser import parse_search_response

FIXTURE = Path(__file__).parent / "fixtures" / "search_response.json"


def test_parse_search_response_returns_summaries_for_all_courses():
    payload = json.loads(FIXTURE.read_text())
    summaries = parse_search_response(payload)
    assert len(summaries) == 2


def test_parse_program_summary_maps_known_fields():
    payload = json.loads(FIXTURE.read_text())
    summaries = parse_search_response(payload)
    additive = next(s for s in summaries if s.id == 10396)

    assert additive.course_name == "Additive Manufacturing"
    assert additive.university == "Paderborn University"
    assert additive.city == "Paderborn"
    assert additive.languages == ["English"]
    assert additive.subject == "Mechanical Engineering"
    assert additive.course_type == 2
    assert additive.has_tuition_fees is False
    assert additive.link == (
        "https://www2.daad.de/deutschland/studienangebote/"
        "international-programmes/en/detail/10396/"
    )


def test_parse_program_summary_detects_paid_tuition():
    payload = {
        "courses": [{
            "id": 1, "courseName": "Test", "courseNameShort": "Test",
            "academy": "Test Uni", "city": "Berlin", "languages": ["English"],
            "subject": "Test Subject", "courseType": 2,
            "programmeDuration": "2 semesters", "beginning": "Winter",
            "tuitionFees": "1500 EUR per semester",
            "link": "/deutschland/studienangebote/international-programmes/en/detail/1/",
        }]
    }
    summaries = parse_search_response(payload)
    assert summaries[0].has_tuition_fees is True
