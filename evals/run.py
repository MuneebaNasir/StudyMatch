"""Run the LLM evaluation and log it to MLflow.

    uv run --extra eval python -m evals.run all
    uv run --extra eval python -m evals.run query --per-provider
    mlflow ui --backend-store-uri sqlite:///mlflow.db

Default mode runs the app's real fallback chains. --per-provider re-runs the
first few cases with each provider forced in turn (see evals/llm_spy.py).
This is the only module that imports MLflow, so the rest of evals/ is
testable without the `eval` extra.
"""
import argparse
import json
import os
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

from .budget import PROVIDERS, estimate_calls
from .datasets import TranscriptCase, load_eligibility_cases, load_program_snapshots, load_query_cases, load_transcript_cases
from .llm_spy import LlmSpy, default_provider_classes
from .scoring import score_eligibility, score_query, score_transcript

SUITES = ("query", "eligibility", "transcript")
EXPERIMENTS = {"query": "query-understanding", "eligibility": "eligibility", "transcript": "transcript"}
# Headline metric per suite for the terminal summary.
HEADLINE = {"query": "all_correct", "eligibility": "verdict_acceptable", "transcript": "course_recall"}
PER_PROVIDER_CASES = 3
CONTENT_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MLFLOW_MISSING = (
    "MLflow isn't installed. Run: uv run --extra eval python -m evals.run <suite>\n"
    "(or `uv sync --extra eval` once, then `uv run python -m evals.run <suite>`)"
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m evals.run", description=__doc__.split("\n\n")[0])
    parser.add_argument("suite", choices=[*SUITES, "all"])
    parser.add_argument("--per-provider", action="store_true", help="run the first few cases once per provider")
    parser.add_argument("--include-transcript-in-per-provider", action="store_true")
    parser.add_argument("--no-judge", action="store_true", help="skip the Groq LLM judge on eligibility")
    parser.add_argument("--gemini-cap", type=int, default=5, help="max Gemini calls per run (default 5)")
    parser.add_argument("--limit", type=int, default=None, help="max cases per suite")
    parser.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    parser.add_argument("--transcript-path", type=Path, help="local real transcript (scores only are logged)")
    parser.add_argument("--truth-path", type=Path, help="ground-truth JSON for --transcript-path")
    parser.add_argument("--tracking-uri", default="sqlite:///mlflow.db")
    return parser.parse_args(argv)


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _model_params() -> dict[str, str]:
    from daad_search.query_understanding import llm as text_llm
    from daad_search.transcript import llm as vision_llm

    return {
        "groq_model": text_llm.GROQ_MODEL, "gemini_model": text_llm.GEMINI_MODEL, "mistral_model": text_llm.MISTRAL_MODEL,
        "groq_vision_model": vision_llm.GROQ_VISION_MODEL, "gemini_vision_model": vision_llm.GEMINI_VISION_MODEL,
        "mistral_vision_model": vision_llm.MISTRAL_VISION_MODEL,
    }


class _RunStats:
    """Per-run bookkeeping the scorers and predict functions write into."""

    def __init__(self):
        self.scores: dict[str, list[float]] = defaultdict(list)
        self.latencies: list[float] = []
        self.tokens = 0
        self.failures = 0
        self.answered_by: Counter = Counter()

    def record_call(self, spy: LlmSpy, latency_s: float, failed: bool) -> dict:
        records = spy.case_records
        tokens = sum((r.input_tokens or 0) + (r.output_tokens or 0) for r in records)
        self.latencies.append(latency_s)
        self.tokens += tokens
        self.failures += int(failed)
        self.answered_by[spy.answered_by() or "none"] += 1
        return {
            "answered_by": spy.answered_by(), "latency_s": round(latency_s, 3), "tokens": tokens,
            "gemini_blocked": any(r.provider == "gemini" and r.blocked for r in records),
        }

    def record_scores(self, scores: dict[str, float]) -> None:
        for name, value in scores.items():
            self.scores[name].append(value)

    def metrics(self) -> dict[str, float]:
        out = {f"mean_{name}": statistics.mean(values) for name, values in self.scores.items()}
        out.update({
            "failures": self.failures, "total_tokens": self.tokens,
            "latency_mean_s": statistics.mean(self.latencies) if self.latencies else 0.0,
            "latency_p50_s": statistics.median(self.latencies) if self.latencies else 0.0,
        })
        out.update({f"answered_by_{name}": count for name, count in self.answered_by.items()})
        return out


def _spied(spy: LlmSpy, stats: _RunStats, call, is_failure) -> tuple:
    spy.start_case()
    start = time.perf_counter()
    with spy:
        try:
            output = call()
        except Exception:
            output = None
    info = stats.record_call(spy, time.perf_counter() - start, failed=output is None or is_failure(output))
    return output, info


def _query_suite(cases, spy, stats, snapshots, judge):
    from mlflow.entities import Feedback
    from mlflow.genai.scorers import scorer

    from daad_search.query_understanding.parser import parse_query
    from daad_search.query_understanding.schema import ParsedQuery

    by_id = {c.id: c for c in cases}

    def predict_fn(case_id: str) -> dict:
        parsed, info = _spied(spy, stats, lambda: parse_query(by_id[case_id].query), lambda out: False)
        return {"parsed": parsed.model_dump() if parsed else None, **info}

    @scorer(name="query_fields")
    def query_fields(outputs, expectations):
        parsed = ParsedQuery(**outputs["parsed"]) if outputs["parsed"] else None
        scores = score_query(by_id[expectations["case_id"]], parsed)
        stats.record_scores(scores)
        return [Feedback(name=name, value=value) for name, value in scores.items()]

    return predict_fn, [query_fields]


def _eligibility_suite(cases, spy, stats, snapshots, judge):
    from mlflow.entities import Feedback
    from mlflow.genai.scorers import scorer

    from daad_search.query_understanding.reasoner import reason_about_eligibility
    from daad_search.query_understanding.schema import CandidateForReasoning, EligibilityVerdict, StudentProfile
    from daad_search.transcript.schema import ExtractedCourse

    from .judge import judge_reasoning

    by_id = {c.id: c for c in cases}

    def predict_fn(case_id: str) -> dict:
        case, snap = by_id[case_id], snapshots[by_id[case_id].program_id]
        candidate = CandidateForReasoning(
            program_id=snap.program_id, course_name=snap.course_name, structured_eligibility=snap.structured_eligibility,
        )
        courses = [ExtractedCourse(**c) for c in case.courses] if case.courses else None
        verdicts, info = _spied(
            spy, stats,
            lambda: reason_about_eligibility(StudentProfile(**case.profile), [candidate], courses),
            lambda out: not any(v.program_id == case.program_id for v in out),
        )
        return {"verdicts": [v.model_dump() for v in verdicts] if verdicts is not None else None, **info}

    def _verdicts(outputs):
        return [EligibilityVerdict(**v) for v in outputs["verdicts"]] if outputs["verdicts"] is not None else None

    @scorer(name="eligibility_verdict")
    def eligibility_verdict(outputs, expectations):
        scores = score_eligibility(by_id[expectations["case_id"]], _verdicts(outputs))
        stats.record_scores(scores)
        return [Feedback(name=name, value=value) for name, value in scores.items()]

    @scorer(name="judge")
    def judge_scorer(outputs, expectations):
        case = by_id[expectations["case_id"]]
        verdict = next((v for v in _verdicts(outputs) or [] if v.program_id == case.program_id), None)
        result = judge_reasoning(case.profile, snapshots[case.program_id], verdict) if verdict else None
        if result is None:
            stats.record_scores({"judge_skipped": 1.0})
            return Feedback(name="judge_supports_verdict", error="judge unavailable or no verdict to judge")
        scores = {
            "judge_skipped": 0.0,
            "judge_supports_verdict": float(result.supports_verdict),
            "judge_no_factual_errors": float(not result.contradicts_case_facts),
        }
        stats.record_scores(scores)
        return [
            Feedback(name="judge_supports_verdict", value=result.supports_verdict, rationale=result.explanation),
            Feedback(name="judge_no_factual_errors", value=not result.contradicts_case_facts, rationale=result.explanation),
        ]

    return predict_fn, [eligibility_verdict, *([judge_scorer] if judge else [])]


def _transcript_suite(cases, spy, stats, snapshots, judge):
    from mlflow.entities import Feedback
    from mlflow.genai.scorers import scorer

    from daad_search.transcript.extractor import extract_transcript
    from daad_search.transcript.schema import TranscriptExtraction

    by_id = {c.id: c for c in cases}

    def predict_fn(case_id: str) -> dict:
        image = by_id[case_id].image_path.read_bytes()
        extraction, info = _spied(spy, stats, lambda: extract_transcript(image, "image/png"), lambda out: not out.courses)
        return {"extraction": extraction.model_dump() if extraction else None, **info}

    @scorer(name="transcript")
    def transcript_scorer(outputs, expectations):
        extraction = TranscriptExtraction(**(outputs["extraction"] or {"extraction_confidence": "low"}))
        scores = score_transcript(by_id[expectations["case_id"]], extraction)
        stats.record_scores(scores)
        return [Feedback(name=name, value=value) for name, value in scores.items()]

    return predict_fn, [transcript_scorer]


SUITE_BUILDERS = {"query": _query_suite, "eligibility": _eligibility_suite, "transcript": _transcript_suite}


def _run_suite(mlflow, suite, provider, cases, spy, snapshots, args) -> dict:
    mlflow.set_experiment(EXPERIMENTS[suite])
    spy.only_provider = provider
    stats = _RunStats()
    gemini_before, blocks_before = spy.gemini_calls, spy.gemini_guard_blocks
    with mlflow.start_run(run_name=f"{suite}/{provider or 'fallback-chain'}"):
        mlflow.log_params({
            "suite": suite, "provider": provider or "fallback-chain", "cases": len(cases),
            "dataset": f"{suite}_cases", "git_sha": _git_sha(), "gemini_cap": args.gemini_cap,
            "judge": suite == "eligibility" and not args.no_judge, **_model_params(),
        })
        predict_fn, scorers = SUITE_BUILDERS[suite](cases, spy, stats, snapshots, not args.no_judge)
        data = [{"inputs": {"case_id": c.id}, "expectations": {"case_id": c.id}} for c in cases]
        mlflow.genai.evaluate(data=data, predict_fn=predict_fn, scorers=scorers)
        metrics = stats.metrics() | {
            "gemini_calls": spy.gemini_calls - gemini_before,
            "gemini_guard_blocks": spy.gemini_guard_blocks - blocks_before,
        }
        mlflow.log_metrics(metrics)
    return {"suite": suite, "provider": provider or "fallback-chain", "cases": len(cases), **metrics}


def _run_private_transcript(mlflow, spy, transcript_path: Path, truth_path: Path) -> dict:
    """Real transcript: no tracing, no per-case inputs/outputs -- only the file
    name, the extracted course names, and aggregate scores are stored."""
    from daad_search.transcript.extractor import extract_transcript

    truth = json.loads(truth_path.read_text())
    case = TranscriptCase(id="private", image_path=transcript_path, courses=truth["courses"], grade_value=truth.get("grade_value"))
    content_type = CONTENT_TYPES.get(transcript_path.suffix.lower(), "application/pdf")
    mlflow.langchain.autolog(disable=True)
    try:
        mlflow.set_experiment(EXPERIMENTS["transcript"])
        spy.only_provider = None
        stats = _RunStats()
        with mlflow.start_run(run_name="transcript/private"):
            extraction, _ = _spied(
                spy, stats, lambda: extract_transcript(transcript_path.read_bytes(), content_type), lambda out: not out.courses,
            )
            scores = score_transcript(case, extraction) if extraction else {"failed": 1.0}
            mlflow.log_param("file_name", transcript_path.name)
            mlflow.log_dict({"course_names": [c.name for c in extraction.courses] if extraction else []}, "course_names.json")
            mlflow.log_metrics(scores)
    finally:
        mlflow.langchain.autolog()
    return {"suite": "transcript", "provider": "private", "cases": 1, **{f"mean_{k}": v for k, v in scores.items()},
            "failures": int(scores.get("failed", 0)), "gemini_calls": 0}


def _print_summary(summaries: list[dict], tracking_uri: str) -> None:
    print(f"\n{'suite':<12} {'provider':<15} {'cases':>5} {'headline':>22} {'failures':>8} {'gemini':>6}")
    for s in summaries:
        name = HEADLINE[s["suite"]]
        value = s.get(f"mean_{name}")
        headline = f"{name} {value:.0%}" if value is not None else "n/a"
        print(f"{s['suite']:<12} {s['provider']:<15} {s['cases']:>5} {headline:>22} {s['failures']:>8} {s.get('gemini_calls', 0):>6}")
    print(f"\nExplore runs and traces: mlflow ui --backend-store-uri {tracking_uri}")


def configure_mlflow_env() -> None:
    # One case at a time: the provider spy keeps per-case state, and parallel
    # cases would also burn through free-tier rate limits.
    os.environ["MLFLOW_GENAI_EVAL_MAX_WORKERS"] = "1"
    # Otherwise evaluate() calls predict_fn an extra time on the first case to
    # validate tracing -- one more LLM call per run, and it skews the stats.
    os.environ["MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION"] = "true"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if bool(args.transcript_path) != bool(args.truth_path):
        print("--transcript-path and --truth-path must be given together.")
        return 2
    try:
        import mlflow
        import mlflow.genai  # noqa: F401
    except ImportError:
        print(MLFLOW_MISSING)
        return 2

    configure_mlflow_env()
    mlflow.set_tracking_uri(args.tracking_uri)

    snapshots = load_program_snapshots()
    loaded = {
        "query": load_query_cases(),
        "eligibility": load_eligibility_cases(snapshots=snapshots),
        "transcript": load_transcript_cases(),
    }
    suites = list(SUITES) if args.suite == "all" else [args.suite]
    cases = {s: loaded[s][: args.limit] for s in suites}
    estimate = estimate_calls(
        suites, {s: len(c) for s, c in cases.items()}, judge=not args.no_judge, per_provider=args.per_provider,
        gemini_cap=args.gemini_cap, per_provider_cases=PER_PROVIDER_CASES,
        include_transcript_in_per_provider=args.include_transcript_in_per_provider,
    )
    extra = " (+1 for your private transcript)" if args.transcript_path else ""
    print(f"This run makes about {estimate['total']} LLM calls{extra}, at most {estimate['gemini_max']} to Gemini "
          f"(cap {args.gemini_cap}). They use the same API keys as the live site.")
    if not args.yes and input("Proceed? [y/N] ").strip().lower() != "y":
        print("Aborted.")
        return 1

    mlflow.langchain.autolog()
    spy = LlmSpy(default_provider_classes(), gemini_cap=args.gemini_cap)
    summaries = []
    for suite in suites:
        if args.per_provider and suite == "transcript" and not args.include_transcript_in_per_provider:
            continue
        for provider in PROVIDERS if args.per_provider else (None,):
            suite_cases = cases[suite][:PER_PROVIDER_CASES] if provider else cases[suite]
            summaries.append(_run_suite(mlflow, suite, provider, suite_cases, spy, snapshots, args))
    if args.transcript_path:
        summaries.append(_run_private_transcript(mlflow, spy, args.transcript_path, args.truth_path))
    _print_summary(summaries, args.tracking_uri)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
