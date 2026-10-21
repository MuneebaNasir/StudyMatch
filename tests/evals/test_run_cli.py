import builtins

from evals import run


def test_main_reports_missing_mlflow_cleanly(monkeypatch, capsys):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mlflow" or name.startswith("mlflow."):
            raise ImportError("No module named 'mlflow'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert run.main(["query", "--yes"]) == 2
    assert "uv run --extra eval python -m evals.run" in capsys.readouterr().out


def test_main_rejects_truth_path_without_transcript_path(capsys):
    assert run.main(["transcript", "--truth-path", "truth.json", "--yes"]) != 0
    assert "--transcript-path" in capsys.readouterr().out


def test_configure_mlflow_env_runs_cases_serially_without_extra_validation_call(monkeypatch):
    monkeypatch.delenv("MLFLOW_GENAI_EVAL_MAX_WORKERS", raising=False)
    monkeypatch.delenv("MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION", raising=False)

    run.configure_mlflow_env()

    import os
    assert os.environ["MLFLOW_GENAI_EVAL_MAX_WORKERS"] == "1"
    # MLflow otherwise calls predict_fn once more on the first case before
    # evaluating, which costs an extra LLM call and skews the stats.
    assert os.environ["MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION"] == "true"
