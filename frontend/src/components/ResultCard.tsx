import type { QueryResult } from "../types";

const VERDICT_STYLES: Record<QueryResult["eligibility_verdict"], string> = {
  eligible: "bg-green-100 text-green-800",
  likely_eligible: "bg-lime-100 text-lime-800",
  not_eligible: "bg-red-100 text-red-800",
  unclear: "bg-amber-100 text-amber-800",
  no_data: "bg-slate-100 text-slate-600",
};

const VERDICT_LABELS: Record<QueryResult["eligibility_verdict"], string> = {
  eligible: "Eligible",
  likely_eligible: "Likely eligible",
  not_eligible: "Not eligible",
  unclear: "Unclear",
  no_data: "Not evaluated",
};

interface ResultCardProps {
  result: QueryResult;
  onClick: (id: number) => void;
}

export function ResultCard({ result, onClick }: ResultCardProps) {
  return (
    <button
      type="button"
      onClick={() => onClick(result.id)}
      className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:border-slate-400"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-medium text-slate-900">{result.course_name}</h3>
          <p className="text-sm text-slate-500">
            {result.university}{result.city ? ` — ${result.city}` : ""}
          </p>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-1 text-xs font-medium ${VERDICT_STYLES[result.eligibility_verdict]}`}>
          {VERDICT_LABELS[result.eligibility_verdict]}
        </span>
      </div>
      {result.eligibility_reasoning && (
        <p className="mt-2 line-clamp-2 text-sm text-slate-600">{result.eligibility_reasoning}</p>
      )}
    </button>
  );
}
