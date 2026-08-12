import collections

import pytest

from daad_search.ingestion import embeddings as embeddings_module
from daad_search.ingestion.embeddings import build_embedding_text


def test_build_embedding_text_combines_all_fields():
    text = build_embedding_text("Data Science MSc", "Computer Science", "Focus on ML and statistics.")
    assert text == "Data Science MSc. Computer Science. Focus on ML and statistics."


def test_build_embedding_text_omits_missing_optional_fields():
    assert build_embedding_text("Data Science MSc", None, None) == "Data Science MSc"
    assert build_embedding_text("Data Science MSc", "Computer Science", None) == (
        "Data Science MSc. Computer Science"
    )


def test_throttle_allows_burst_then_waits_for_the_window(monkeypatch):
    monkeypatch.setattr(embeddings_module, "_voyage_call_times", collections.deque())

    fake_now = [1000.0]
    sleeps = []

    def fake_monotonic():
        return fake_now[0]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        fake_now[0] += seconds

    monkeypatch.setattr(embeddings_module.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(embeddings_module.time, "sleep", fake_sleep)

    # First 3 calls (the per-minute budget) go through with no waiting.
    for _ in range(embeddings_module.VOYAGE_REQUESTS_PER_MINUTE):
        embeddings_module._throttle_to_voyage_rate_limit()
    assert sleeps == []

    # The 4th call must wait for the 1st call to fall outside the 60s window.
    embeddings_module._throttle_to_voyage_rate_limit()
    assert sleeps == [60.0]
    assert fake_now[0] == 1060.0


def test_embed_texts_throttles_before_calling_the_client(monkeypatch):
    monkeypatch.setattr(embeddings_module.settings, "embedding_provider", "voyage")
    calls = []
    monkeypatch.setattr(
        embeddings_module, "_throttle_to_voyage_rate_limit", lambda: calls.append("throttle")
    )

    class FakeResult:
        embeddings = [[0.1, 0.2]]

    class FakeClient:
        def embed(self, texts, model, input_type):
            calls.append("embed")
            return FakeResult()

    result = embeddings_module.embed_texts(["hello"], client=FakeClient())
    assert calls == ["throttle", "embed"]
    assert result == [[0.1, 0.2]]


def test_embed_texts_dispatches_to_local_provider(monkeypatch):
    monkeypatch.setattr(embeddings_module.settings, "embedding_provider", "local")
    monkeypatch.setattr(
        embeddings_module, "_embed_texts_local", lambda texts, input_type: [[9.0] * 3]
    )
    voyage_calls = []
    monkeypatch.setattr(
        embeddings_module, "_embed_texts_voyage",
        lambda *a, **kw: voyage_calls.append((a, kw)) or [[0.0]],
    )

    assert embeddings_module.embed_texts(["x"]) == [[9.0] * 3]
    assert voyage_calls == []


def test_embed_texts_dispatches_to_voyage_when_configured(monkeypatch):
    monkeypatch.setattr(embeddings_module.settings, "embedding_provider", "voyage")
    local_calls = []
    monkeypatch.setattr(
        embeddings_module, "_embed_texts_local",
        lambda *a, **kw: local_calls.append((a, kw)) or [[0.0]],
    )
    monkeypatch.setattr(
        embeddings_module, "_embed_texts_voyage", lambda texts, input_type, client=None: [[1.0]]
    )

    assert embeddings_module.embed_texts(["x"]) == [[1.0]]
    assert local_calls == []


def test_local_provider_applies_query_instruction_only_to_queries(monkeypatch):
    class FakeVector:
        def tolist(self):
            return [[1.0, 2.0]]

    class FakeModel:
        def __init__(self):
            self.seen_texts = None

        def encode(self, texts, normalize_embeddings):
            self.seen_texts = texts
            assert normalize_embeddings is True
            return FakeVector()

    fake_model = FakeModel()
    monkeypatch.setattr(embeddings_module, "_local_model", fake_model)

    embeddings_module._embed_texts_local(["machine learning"], "document")
    assert fake_model.seen_texts == ["machine learning"]

    embeddings_module._embed_texts_local(["machine learning"], "query")
    assert fake_model.seen_texts == [
        embeddings_module.LOCAL_QUERY_INSTRUCTION + "machine learning"
    ]


def test_get_local_model_returns_a_singleton(monkeypatch):
    monkeypatch.setattr(embeddings_module, "_local_model", None)

    class FakeSentenceTransformer:
        def __init__(self, name, local_files_only=False):
            self.name = name
            self.local_files_only = local_files_only

    monkeypatch.setattr(
        "sentence_transformers.SentenceTransformer", FakeSentenceTransformer
    )
    monkeypatch.setattr("torch.set_num_threads", lambda n: None)

    first = embeddings_module.get_local_model()
    assert isinstance(first, FakeSentenceTransformer)
    assert embeddings_module.get_local_model() is first


def test_get_local_model_caps_torch_threads_to_detected_quota(monkeypatch):
    monkeypatch.setattr(embeddings_module, "_local_model", None)

    class FakeSentenceTransformer:
        def __init__(self, name, local_files_only=False):
            pass

    monkeypatch.setattr(
        "sentence_transformers.SentenceTransformer", FakeSentenceTransformer
    )
    monkeypatch.setattr(embeddings_module, "_detect_cpu_quota", lambda: 2)

    set_threads_calls = []
    monkeypatch.setattr("torch.set_num_threads", lambda n: set_threads_calls.append(n))

    embeddings_module.get_local_model()

    assert set_threads_calls == [2]


def test_configure_torch_threads_prefers_cgroup_quota_over_affinity(monkeypatch):
    # Regression: os.sched_getaffinity reported 4 CPUs inside a Cloud Run
    # container configured with a 2-vCPU cgroup quota -- affinity reports
    # which cores are visible, not how much compute time is actually
    # granted, and trusting it caused severe CFS-throttling slowdowns.
    monkeypatch.setattr(embeddings_module, "_detect_cpu_quota", lambda: 2)
    monkeypatch.setattr(
        embeddings_module.os, "sched_getaffinity", lambda pid: {0, 1, 2, 3}, raising=False
    )

    set_threads_calls = []
    monkeypatch.setattr("torch.set_num_threads", lambda n: set_threads_calls.append(n))

    embeddings_module._configure_torch_threads()

    assert set_threads_calls == [2]


def test_configure_torch_threads_falls_back_to_affinity_without_quota(monkeypatch):
    monkeypatch.setattr(embeddings_module, "_detect_cpu_quota", lambda: None)
    monkeypatch.setattr(
        embeddings_module.os, "sched_getaffinity", lambda pid: {0, 1}, raising=False
    )

    set_threads_calls = []
    monkeypatch.setattr("torch.set_num_threads", lambda n: set_threads_calls.append(n))

    embeddings_module._configure_torch_threads()

    assert set_threads_calls == [2]


def test_configure_torch_threads_falls_back_to_cpu_count_without_quota_or_affinity(monkeypatch):
    monkeypatch.setattr(embeddings_module, "_detect_cpu_quota", lambda: None)
    monkeypatch.delattr(embeddings_module.os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(embeddings_module.os, "cpu_count", lambda: 4)

    set_threads_calls = []
    monkeypatch.setattr("torch.set_num_threads", lambda n: set_threads_calls.append(n))

    embeddings_module._configure_torch_threads()

    assert set_threads_calls == [4]


def test_detect_cpu_quota_reads_cgroup_v2_format(monkeypatch, tmp_path):
    cgroup_file = tmp_path / "cpu.max"
    cgroup_file.write_text("200000 100000\n")

    real_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/sys/fs/cgroup/cpu.max":
            return real_open(cgroup_file, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    assert embeddings_module._detect_cpu_quota() == 2


def test_detect_cpu_quota_returns_none_for_unlimited_cgroup_v2(monkeypatch, tmp_path):
    cgroup_file = tmp_path / "cpu.max"
    cgroup_file.write_text("max 100000\n")

    real_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/sys/fs/cgroup/cpu.max":
            return real_open(cgroup_file, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    assert embeddings_module._detect_cpu_quota() is None


def test_detect_cpu_quota_falls_back_to_cgroup_v1_format(monkeypatch, tmp_path):
    quota_file = tmp_path / "cfs_quota_us"
    quota_file.write_text("400000")
    period_file = tmp_path / "cfs_period_us"
    period_file.write_text("100000")

    real_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/sys/fs/cgroup/cpu.max":
            raise FileNotFoundError(path)
        if path == "/sys/fs/cgroup/cpu/cpu.cfs_quota_us":
            return real_open(quota_file, *args, **kwargs)
        if path == "/sys/fs/cgroup/cpu/cpu.cfs_period_us":
            return real_open(period_file, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    assert embeddings_module._detect_cpu_quota() == 4


def test_detect_cpu_quota_returns_none_when_no_cgroup_files_exist(monkeypatch):
    def fake_open(path, *args, **kwargs):
        raise FileNotFoundError(path)

    monkeypatch.setattr("builtins.open", fake_open)

    assert embeddings_module._detect_cpu_quota() is None


def test_get_qdrant_client_returns_a_singleton(monkeypatch):
    monkeypatch.setattr(embeddings_module, "_qdrant_client", None)
    first = embeddings_module.get_qdrant_client()
    assert embeddings_module.get_qdrant_client() is first


def test_with_retry_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(embeddings_module.time, "sleep", lambda _: None)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return "ok"

    assert embeddings_module.with_retry(flaky) == "ok"
    assert len(calls) == 3


def test_with_retry_reraises_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr(embeddings_module.time, "sleep", lambda _: None)

    def always_fails():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        embeddings_module.with_retry(always_fails)


@pytest.mark.integration
def test_ensure_collection_and_upsert_embedding_roundtrip(test_qdrant):
    from daad_search.ingestion.embeddings import EMBEDDING_DIM, upsert_embedding

    vector = [0.1] * EMBEDDING_DIM
    upsert_embedding(test_qdrant, 999, vector, {"program_id": 999, "subject": "Test"})

    points = test_qdrant.retrieve(
        collection_name=embeddings_module.COLLECTION_NAME, ids=[999]
    )
    assert len(points) == 1
    assert points[0].payload["subject"] == "Test"
