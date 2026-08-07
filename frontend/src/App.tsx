import { useState } from "react";

import { AdmissionGuideDrawer } from "./components/AdmissionGuideDrawer";
import { ChatQueryBox } from "./components/ChatQueryBox";
import { Header } from "./components/Header";
import { ExtractionSummary } from "./components/ExtractionSummary";
import { Pagination } from "./components/Pagination";
import { ResultsList } from "./components/ResultsList";
import { useFilteredSearch } from "./hooks/useFilteredSearch";
import { useProgramDetail } from "./hooks/useProgramDetail";
import { useQuerySearch } from "./hooks/useQuerySearch";
import { buildVerdictMap, mergeVerdicts, type VerdictInfo } from "./lib/mergeVerdicts";
import type { QueryResponse, QueryResult, SearchFilters } from "./types";

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
  const [displayedResults, setDisplayedResults] = useState<QueryResult[]>([]);
  const [activeFilters, setActiveFilters] = useState<SearchFilters | null>(null);
  const [verdictMap, setVerdictMap] = useState<Map<number, VerdictInfo>>(new Map());
  const [selectedProgramId, setSelectedProgramId] = useState<number | null>(null);
  const [activeQuery, setActiveQuery] = useState<ActiveQuery | null>(null);
  const [offset, setOffset] = useState(0);
  const [totalMatched, setTotalMatched] = useState(0);

  const querySearch = useQuerySearch();
  const filteredSearch = useFilteredSearch();
  const programDetail = useProgramDetail(selectedProgramId);

  function runQuerySearch(query: string, offset: number) {
    setActiveQuery({ type: "query", query });
    querySearch.mutate(
      { query, offset },
      {
        onSuccess: (response) => {
          setQueryResponse(response);
          setDisplayedResults(response.results);
          setActiveFilters(response.extracted_filters);
          setVerdictMap(buildVerdictMap(response.results));
          setTotalMatched(response.total_matched);
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
          setDisplayedResults(mergeVerdicts(response.results, verdictMap));
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
    runQuerySearch(query, 0);
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
    setSelectedProgramId(null);
    setActiveQuery(null);
    setOffset(0);
    setTotalMatched(0);
    querySearch.reset();
    filteredSearch.reset();
  }

  const hasSubmitted = querySearch.isPending || queryResponse !== null;
  const selectedVerdictInfo = selectedProgramId !== null ? verdictMap.get(selectedProgramId) : undefined;
  const selectedVerdict = selectedVerdictInfo
    ? { eligibility_verdict: selectedVerdictInfo.verdict, eligibility_reasoning: selectedVerdictInfo.reasoning }
    : null;

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <Header />
      <ChatQueryBox onSubmit={handleSubmit} isPending={querySearch.isPending} />

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
                className="shrink-0 text-sm text-slate-400 hover:text-slate-700"
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
            results={displayedResults}
            isLoading={querySearch.isPending || filteredSearch.isPending}
            onSelectProgram={setSelectedProgramId}
          />

          <Pagination offset={offset} limit={PAGE_SIZE} total={totalMatched} onPageChange={handlePageChange} />
        </>
      )}

      <AdmissionGuideDrawer
        programId={selectedProgramId}
        verdict={selectedVerdict}
        program={programDetail.data}
        isLoading={programDetail.isLoading}
        isError={programDetail.isError}
        onClose={() => setSelectedProgramId(null)}
      />
    </main>
  );
}
