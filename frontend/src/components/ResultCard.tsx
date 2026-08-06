import { VERDICT_LABELS, VERDICT_STYLES } from "../lib/verdictDisplay";
import type { QueryResult } from "../types";

interface ResultCardProps {
  result: QueryResult;
  onClick: (id: number) => void;
}

function buildMetaLine(result: QueryResult): string {
  const parts: string[] = [];
  if (result.languages.length > 0) parts.push(result.languages.join(", "));
  if (result.tuition_fees_text) parts.push(result.tuition_fees_text);
  if (result.application_deadline_text) parts.push(result.application_deadline_text);
  return parts.join(" · ");
}

export function ResultCard({ result, onClick }: ResultCardProps) {
  const metaLine = buildMetaLine(result);
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
      {metaLine && <p className="mt-1 text-xs text-slate-400">{metaLine}</p>}
      {result.eligibility_reasoning && (
        <p className="mt-2 line-clamp-2 text-sm text-slate-600">{result.eligibility_reasoning}</p>
      )}
    </button>
  );
}
