from daad_search.query_understanding.schema import EligibilityVerdict
from evals.datasets import ProgramSnapshot
from evals.judge import build_judge_prompt

PROGRAM = ProgramSnapshot(program_id=1, course_name="CS", structured_eligibility={"grade_requirement": {"value": 2.5}})
VERDICT = EligibilityVerdict(program_id=1, verdict="eligible", reasoning="3.0 GPA is German 2.0")


def test_judge_prompt_includes_the_apps_own_german_grade_conversion():
    prompt = build_judge_prompt({"grade_value": 3.0, "grade_scale": "4.0 GPA"}, PROGRAM, VERDICT)

    # Without the reference value, the judge flagged this correct conversion as a factual error.
    assert "German-scale equivalent: 2.0" in prompt


def test_judge_prompt_omits_conversion_for_unknown_scales():
    prompt = build_judge_prompt({"grade_value": 1.7, "grade_scale": "German grading scale"}, PROGRAM, VERDICT)

    assert "German-scale equivalent" not in prompt


def test_judge_uses_groq_json_schema_mode(monkeypatch):
    # gpt-oss on Groq often ignores forced tool calls (400 tool_use_failed);
    # JSON-schema mode was 3/3 where tool calling was 1/3 in a live check.
    from evals import judge

    captured = {}

    class FakeGroq:
        def __init__(self, **kwargs):
            pass

        def with_structured_output(self, schema, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop here")

    monkeypatch.setattr(judge, "ChatGroq", FakeGroq)

    assert judge.judge_reasoning({}, PROGRAM, VERDICT) is None
    assert captured == {"method": "json_schema"}
