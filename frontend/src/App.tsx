import { useMemo, useState } from "react";

import { AdmissionGuideDrawer } from "./components/AdmissionGuideDrawer";
import { ChatQueryBox } from "./components/ChatQueryBox";
import { ExtractionSummary } from "./components/ExtractionSummary";
import { Header } from "./components/Header";
import { Pagination } from "./components/Pagination";
import { ResultsList } from "./components/ResultsList";
import { useFilteredSearch } from "./hooks/useFilteredSearch";
import { useProgramDetail } from "./hooks/useProgramDetail";
import { useQuerySearch } from "./hooks/useQuerySearch";
import { buildVerdictMap, mergeVerdicts, type VerdictInfo } from "./lib/mergeVerdicts";
import type { EligibilityVerdictValue, QueryResponse, SearchFilters, SearchResult } from "./types";

const PAGE_SIZE = 20;

type ActiveQuery =
  | { type: "query"; query: string }
  | { type: "filters"; filters: SearchFilters; semanticQuery: string | null };

function ErrorBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
      <span>Something went wrong.</span>
      <button type="button" onClick={onRetry} className="font-medium underline">
        Retry
      </button>
    </div>
  );
}

export default function App() {
  const [queryResponse, setQueryResponse] = useState<QueryResponse | null>(null);
  const [displayedResults, setDisplayedResults] = useState<SearchResult[]>([]);
  const [activeFilters, setActiveFilters] = useState<SearchFilters | null>(null);
  const [verdictMap, setVerdictMap] = useState<Map<number, VerdictInfo>>(new Map());
  const [selectedProgramId, setSelectedProgramId] = useState<number | null>(null);
  const [activeQuery, setActiveQuery] = useState<ActiveQuery | null>(null);
  const [offset, setOffset] = useState(0);
  const [totalMatched, setTotalMatched] = useState(0);
  const [pageCache, setPageCache] = useState<Map<number, QueryResponse>>(new Map());

  const querySearch = useQuerySearch();
  const filteredSearch = useFilteredSearch();
  const programDetail = useProgramDetail(selectedProgramId);

  const resultsForDisplay = useMemo(
    () => mergeVerdicts(displayedResults, verdictMap),
    [displayedResults, verdictMap],
  );

  function runQuerySearch(query: string, offset: number, options: { skipCache?: boolean } = {}) {
    setActiveQuery({ type: "query", query });
    const cached = options.skipCache ? undefined : pageCache.get(offset);
    if (cached) {
      setQueryResponse(cached);
      setDisplayedResults(cached.results);
      setActiveFilters(cached.extracted_filters);
      setTotalMatched(cached.total_matched);
      // Deliberately does NOT touch verdictMap. pageCache holds a frozen
      // snapshot from whenever this page was first fetched; if the user
      // evaluated a program on-demand since then, verdictMap already holds
      // a more current value than the snapshot does for that id. Re-merging
      // the stale snapshot would overwrite it. resultsForDisplay always
      // reads verdicts from the live verdictMap, never from what's baked
      // into displayedResults/the cached response, so leaving it alone here
      // is correct.
      return;
    }
    querySearch.mutate(
      { query, offset },
      {
        onSuccess: (response) => {
          setPageCache((previous) => new Map(previous).set(offset, response));
          setQueryResponse(response);
          setDisplayedResults(response.results);
          setActiveFilters(response.extracted_filters);
          setTotalMatched(response.total_matched);
          setVerdictMap((previous) => {
            const merged = new Map(previous);
            for (const [id, info] of buildVerdictMap(response.results)) {
              merged.set(id, info);
            }
            return merged;
          });
        },
      },
    );
  }

  function runFilteredSearch(filters: SearchFilters, semanticQuery: string | null, offset: number) {
    const previousFilters = activeFilters;
    const previousActiveQuery = activeQuery;
    setActiveFilters(filters);
    setActiveQuery({ type: "filters", filters, semanticQuery });
    filteredSearch.mutate(
      { filters, semanticQuery, offset },
      {
        onSuccess: (response) => {
          setDisplayedResults(response.results);
          setTotalMatched(response.total_matched);
        },
        onError: () => {
          setActiveFilters(previousFilters);
          setActiveQuery(previousActiveQuery);
        },
      },
    );
  }

  function handleSubmit(query: string) {
    setOffset(0);
    setPageCache(new Map());
    // skipCache: true because setPageCache above only schedules a
    // re-render — pageCache in this closure is still the pre-clear map
    // from the current render, so without skipCache a second distinct
    // search could hit a stale cache entry from the previous query.
    runQuerySearch(query, 0, { skipCache: true });
  }

  function handleFiltersChange(filters: SearchFilters) {
    setOffset(0);
    runFilteredSearch(filters, queryResponse?.semantic_query ?? null, 0);
  }

  function handlePageChange(newOffset: number) {
    if (!activeQuery) return;
    setOffset(newOffset);
    if (activeQuery.type === "query") {
      runQuerySearch(activeQuery.query, newOffset);
    } else {
      runFilteredSearch(activeQuery.filters, activeQuery.semanticQuery, newOffset);
    }
  }

  function handleStartOver() {
    setQueryResponse(null);
    setDisplayedResults([]);
    setActiveFilters(null);
    setVerdictMap(new Map());
    setPageCache(new Map());
    setSelectedProgramId(null);
    setActiveQuery(null);
    setOffset(0);
    setTotalMatched(0);
    querySearch.reset();
    filteredSearch.reset();
  }

  function handleEligibilityEvaluated(
    programId: number, verdict: EligibilityVerdictValue, reasoning: string | null,
  ) {
    setVerdictMap((previous) => {
      const next = new Map(previous);
      next.set(programId, { verdict, reasoning });
      return next;
    });
  }

  const hasSubmitted = querySearch.isPending || queryResponse !== null;
  const selectedVerdictInfo = selectedProgramId !== null ? verdictMap.get(selectedProgramId) : undefined;
  const selectedVerdict = selectedVerdictInfo
    ? { eligibility_verdict: selectedVerdictInfo.verdict, eligibility_reasoning: selectedVerdictInfo.reasoning }
    : null;

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="relative overflow-hidden rounded-3xl bg-accent-soft p-6 sm:p-8">
        <span className="pointer-events-none absolute left-4 top-4 text-2xl opacity-30" aria-hidden="true">🎓</span>
        <span className="pointer-events-none absolute right-6 top-6 text-xl opacity-25" aria-hidden="true">🏰</span>
        <span className="pointer-events-none absolute bottom-4 left-10 text-xl opacity-25" aria-hidden="true">🥨</span>
        <span className="pointer-events-none absolute bottom-6 right-10 text-2xl opacity-30" aria-hidden="true">✈️</span>
        <span className="pointer-events-none absolute right-1/3 top-1/2 text-lg opacity-20" aria-hidden="true">📚</span>
        <Header />
        <ChatQueryBox onSubmit={handleSubmit} isPending={querySearch.isPending} />
      </div>

      {querySearch.isError && (
        <ErrorBanner
          onRetry={() =>
            querySearch.variables !== undefined &&
            runQuerySearch(querySearch.variables.query, querySearch.variables.offset)
          }
        />
      )}

      {hasSubmitted && (
        <>
          {queryResponse && (
            <div className="flex items-center justify-between gap-4">
              <ExtractionSummary
                filters={activeFilters}
                profile={queryResponse.extracted_profile}
                onFiltersChange={handleFiltersChange}
              />
              <button
                type="button"
                onClick={handleStartOver}
                className="shrink-0 text-sm text-ink/40 hover:text-ink"
              >
                Start over
              </button>
            </div>
          )}

          {filteredSearch.isError && (
            <ErrorBanner
              onRetry={() =>
                filteredSearch.variables !== undefined &&
                runFilteredSearch(
                  filteredSearch.variables.filters,
                  filteredSearch.variables.semanticQuery,
                  filteredSearch.variables.offset,
                )
              }
            />
          )}

          <ResultsList
            results={resultsForDisplay}
            isLoading={filteredSearch.isPending}
            isInitialQueryPending={querySearch.isPending && offset === 0}
            isPaginationPending={querySearch.isPending && offset > 0}
            onSelectProgram={setSelectedProgramId}
          />

          <Pagination offset={offset} limit={PAGE_SIZE} total={totalMatched} onPageChange={handlePageChange} />
        </>
      )}

      <AdmissionGuideDrawer
        programId={selectedProgramId}
        verdict={selectedVerdict}
        profile={queryResponse?.extracted_profile ?? null}
        program={programDetail.data}
        isLoading={programDetail.isLoading}
        isError={programDetail.isError}
        onClose={() => setSelectedProgramId(null)}
        onEligibilityEvaluated={handleEligibilityEvaluated}
      />
    </main>
  );
}
