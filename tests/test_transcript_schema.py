from daad_search.transcript.schema import ExtractedCourse, TranscriptExtraction


def test_transcript_extraction_defaults_to_empty_courses():
    extraction = TranscriptExtraction(extraction_confidence="low")
    assert extraction.courses == []
    assert extraction.grade_value is None


def test_extracted_course_requires_only_a_name():
    course = ExtractedCourse(name="Linear Algebra")
    assert course.grade is None
