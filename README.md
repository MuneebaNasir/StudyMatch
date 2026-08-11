# Study in Germany — DAAD Program Search

Natural-language search over ~2,400 real DAAD (German Academic Exchange Service) master's/PhD programs, with LLM-based eligibility reasoning against a student's own background.

**Live demo:** https://frontend-snowy-ten-66.vercel.app
**API:** https://daad-search-api-1032065198351.us-central1.run.app

## The problem

International students trying to study in Germany face a huge, unstructured catalog of programs and admission requirements written in inconsistent legal/academic language. It's hard to know what to search for, and harder still to tell whether you're actually eligible for a given program.

## What it does

- Type a free-text query (e.g. *"Master's in robotics, taught in English, no tuition fees, near Berlin — I have a 3.2 GPA on a 4.0 scale from Pakistan"*) and get back matching programs.
- The query is parsed by an LLM into structured filters (subject, city, language, degree level, tuition) **and** a semantic-search query **and** a structured student profile — not passed to search as raw text.
- Search is hybrid: hard filters against Postgres + semantic similarity against Qdrant (vector DB), covering both exact constraints and fuzzy topic matching.
- Eligibility isn't raw-text matching: a separate extraction pipeline pre-structures each program's admission requirements (grade thresholds, language tests, degree prerequisites) ahead of time. At query time, the LLM reasons over two structured representations — the program's requirements and the student's profile — not two blobs of text.
- Grade conversion to the German scale (1.0 best–5.0 worst) is done deterministically in code (not left to the LLM to compute), then handed to the LLM as a precomputed fact.

## Architecture

```
React (Vite + TS) ─▶ FastAPI + async SQLAlchemy ─▶ Postgres (structured data)
                                │                └─▶ Qdrant (vector search)
                                └─▶ LangChain fallback chain: Groq → Mistral → Gemini
```

- **Frontend:** React, TypeScript, Vite, TanStack Query, Radix UI, Tailwind CSS.
- **Backend:** FastAPI, SQLAlchemy (async), Pydantic.
- **Data:** Postgres (structured program data), Qdrant (hybrid/vector search).
- **LLM layer:** LangChain, with a `.with_fallbacks()` chain across three free-tier providers (Groq → Mistral → Gemini) so a single provider's rate limit or outage doesn't take the app down.
- **Deployment:** Vercel (frontend) + Google Cloud Run (backend, scale-to-zero) + Neon (Postgres) + Qdrant Cloud — all on free tiers.

## Notable engineering decisions

- **Cost-aware eligibility reasoning:** the most expensive LLM call (batch eligibility reasoning) runs automatically only for the top-ranked candidate; the rest are evaluated on demand, cutting default per-query token cost by ~90%.
- **Graceful degradation, not hard failure:** if query parsing fails on every LLM provider, the app falls back to pure semantic search over the raw query text instead of erroring; if embedding/Qdrant fails, it degrades to filtered DB-only search.
- **Deterministic math kept out of the LLM's hands:** grade-scale conversion uses a fixed formula in code, because weaker fallback-tier models were observed getting the comparison direction wrong.
- **Structured production logging:** every query logs the raw input, which LLM provider actually responded, the extracted filters/profile, and (for eligibility) the exact structured inputs fed to the reasoning call — so real production behavior is inspectable after the fact.

## Running locally

```bash
# Backend
docker compose up -d          # Postgres + Qdrant
cp .env.example .env          # fill in your own API keys
uv sync --extra dev
uv run uvicorn daad_search.api.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Run tests: `uv run pytest -m "not integration"` (backend) and `npm test` (frontend, from `frontend/`).

## License

MIT
