import type { QueryResult } from "../types";
import { ResultCard } from "./ResultCard";
import { TurboSnailLoader } from "./TurboSnailLoader";

interface ResultsListProps {
  results: QueryResult[];
  isLoading: boolean;
  isQueryPending: boolean;
  onSelectProgram: (id: number) => void;
}

export function ResultsList({ results, isLoading, isQueryPending, onSelectProgram }: ResultsListProps) {
  if (isQueryPending) {
    return <TurboSnailLoader />;
  }

  if (isLoading) {
    return (
      <div className="space-y-3" data-testid="results-loading">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-2xl bg-line/50" />
        ))}
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <p className="text-sm text-ink/70">No programs matched — try loosening a filter or rephrasing.</p>
    );
  }

  return (
    <div className="space-y-3">
      {results.map((result) => (
        <ResultCard key={result.id} result={result} onClick={onSelectProgram} />
      ))}
    </div>
  );
}
