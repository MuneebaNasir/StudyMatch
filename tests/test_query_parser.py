# tests/test_query_parser.py
import pytest

from daad_search.query_understanding.parser import build_query_prompt, parse_query


def test_build_query_prompt_includes_the_raw_query():
    prompt = build_query_prompt("masters in robotics, no fee, English taught")
    assert "masters in robotics, no fee, English taught" in prompt


def test_build_query_prompt_documents_course_type_codes():
    prompt = build_query_prompt("anything")
    assert "2=Master's" in prompt


def test_parse_query_returns_none_when_all_providers_fail(monkeypatch):
    from daad_search.query_understanding import parser as parser_module

    class AlwaysFailsChain:
        def invoke(self, prompt):
            raise RuntimeError("all providers exhausted")

    monkeypatch.setattr(parser_module, "get_fallback_llm", lambda schema: AlwaysFailsChain())

    assert parse_query("anything") is None


@pytest.mark.integration
def test_parse_query_extracts_filters_and_student_profile():
    result = parse_query(
        "I have a bachelors in Artificial Intelligence from Pakistan with CGPA 3.2, "
        "and I want English-taught, no-fee master's programs in Germany"
    )
    assert result is not None
    assert result.filters.max_tuition_free_only is True
    assert "English" in (result.filters.languages or [])
    assert result.filters.course_type == 2
    assert result.student_profile.grade_value == 3.2
    assert result.student_profile.nationality is not None
    assert "pakistan" in result.student_profile.nationality.lower()


@pytest.mark.integration
def test_parse_query_does_not_treat_country_as_city():
    # This is a Germany-only catalog, so "in germany" is not a city filter --
    # every program already matches it. Only an actual city name (e.g. "Berlin")
    # should populate filters.city.
    result = parse_query(
        "I am looking for Masters in AI, agentic AI, LLM, in germany with no "
        "tution fee and taught only in english"
    )
    assert result is not None
    assert result.filters.city is None
