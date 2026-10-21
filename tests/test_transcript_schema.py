from daad_search.transcript.schema import ExtractedCourse, TranscriptExtraction


def test_transcript_extraction_defaults_to_empty_courses():
    extraction = TranscriptExtraction(extraction_confidence="low")
    assert extraction.courses == []
    assert extraction.grade_value is None


def test_extracted_course_requires_only_a_name():
    course = ExtractedCourse(name="Linear Algebra")
    assert course.grade is None


def test_transcript_extraction_defaults_confidence_when_the_model_omits_it():
    # ministral-14b leaves this field out of roughly half its tool calls; when
    # it was required, those calls discarded an otherwise complete course list.
    extraction = TranscriptExtraction.model_validate(
        {"courses": [{"name": "Data Structures", "grade": "B+"}], "grade_value": 3.24}
    )

    assert extraction.extraction_confidence == "medium"
    assert extraction.courses[0].name == "Data Structures"
