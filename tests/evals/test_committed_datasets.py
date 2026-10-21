import json

from evals.datasets import DATASETS_DIR, load_eligibility_cases, load_query_cases, load_transcript_cases
from evals.make_synthetic_transcripts import write_cases


def test_committed_query_cases_load():
    assert len(load_query_cases()) == 10


def test_committed_eligibility_cases_load_with_snapshots():
    assert len(load_eligibility_cases()) == 10


def test_committed_transcript_cases_load():
    cases = load_transcript_cases()

    assert [c.id for c in cases] == ["synthetic_clean", "synthetic_scan"]
    assert all(c.image_path.exists() for c in cases)


def test_synthetic_transcript_generator_is_deterministic(tmp_path):
    write_cases(tmp_path)

    for case_id in ("synthetic_clean", "synthetic_scan"):
        regenerated = json.loads((tmp_path / f"{case_id}.json").read_text())
        committed = json.loads((DATASETS_DIR / "transcripts" / f"{case_id}.json").read_text())
        assert regenerated == committed
