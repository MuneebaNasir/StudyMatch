from evals.budget import estimate_calls

COUNTS = {"query": 10, "eligibility": 10, "transcript": 2}


def test_estimate_default_all_with_judge():
    estimate = estimate_calls(["query", "eligibility", "transcript"], COUNTS, judge=True, per_provider=False, gemini_cap=5)

    assert estimate["total"] == 32
    assert estimate["gemini_max"] == 5


def test_estimate_per_provider_excludes_transcript_by_default():
    estimate = estimate_calls(["query", "eligibility", "transcript"], COUNTS, judge=False, per_provider=True, gemini_cap=5)

    assert estimate["total"] == 3 * 3 * 2


def test_estimate_gemini_max_is_transcripts_plus_text_fallbacks_when_under_cap():
    estimate = estimate_calls(["query", "transcript"], {"query": 2, "transcript": 1}, judge=True, per_provider=False, gemini_cap=5)

    assert estimate["gemini_max"] == 3
