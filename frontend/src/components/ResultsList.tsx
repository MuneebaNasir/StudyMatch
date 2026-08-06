import type { QueryResult } from "../types";
import { ResultCard } from "./ResultCard";

interface ResultsListProps {
  results: QueryResult[];
  isLoading: boolean;
  onSelectProgram: (id: number) => void;
}

export function ResultsList({ results, isLoading, onSelectProgram }: ResultsListProps) {
  if (isLoading) {
    return (
      <div className="space-y-3" data-testid="results-loading">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100" />
        ))}
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <p className="text-sm text-slate-500">No programs matched — try loosening a filter or rephrasing.</p>
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
