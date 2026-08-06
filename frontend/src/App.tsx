import { useState } from "react";

import { AdmissionGuideDrawer } from "./components/AdmissionGuideDrawer";
import { ChatQueryBox } from "./components/ChatQueryBox";
import { ExtractionSummary } from "./components/ExtractionSummary";
import { ResultsList } from "./components/ResultsList";
import { useFilteredSearch } from "./hooks/useFilteredSearch";
import { useProgramDetail } from "./hooks/useProgramDetail";
import { useQuerySearch } from "./hooks/useQuerySearch";
import { buildVerdictMap, mergeVerdicts, type VerdictInfo } from "./lib/mergeVerdicts";
import type { QueryResponse, QueryResult, SearchFilters } from "./types";

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

  const querySearch = useQuerySearch();
  const filteredSearch = useFilteredSearch();
  const programDetail = useProgramDetail(selectedProgramId);

  function handleSubmit(query: string) {
    querySearch.mutate(query, {
      onSuccess: (response) => {
        setQueryResponse(response);
        setDisplayedResults(response.results);
        setActiveFilters(response.extracted_filters);
        setVerdictMap(buildVerdictMap(response.results));
      },
    });
  }

  function handleFiltersChange(filters: SearchFilters) {
    const previousFilters = activeFilters;
    setActiveFilters(filters);
    filteredSearch.mutate(
      { filters, semanticQuery: queryResponse?.semantic_query ?? null },
      {
        onSuccess: (response) => {
          setDisplayedResults(mergeVerdicts(response.results, verdictMap));
        },
        onError: () => {
          setActiveFilters(previousFilters);
        },
      },
    );
  }

  function handleStartOver() {
    setQueryResponse(null);
    setDisplayedResults([]);
    setActiveFilters(null);
    setVerdictMap(new Map());
    setSelectedProgramId(null);
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
      <h1 className="text-2xl font-semibold text-slate-900">DAAD Program Search</h1>
      <ChatQueryBox onSubmit={handleSubmit} isPending={querySearch.isPending} />

      {querySearch.isError && (
        <ErrorBanner onRetry={() => querySearch.variables !== undefined && handleSubmit(querySearch.variables)} />
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
                filteredSearch.variables !== undefined && handleFiltersChange(filteredSearch.variables.filters)
              }
            />
          )}

          <ResultsList
            results={displayedResults}
            isLoading={querySearch.isPending || filteredSearch.isPending}
            onSelectProgram={setSelectedProgramId}
          />
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
