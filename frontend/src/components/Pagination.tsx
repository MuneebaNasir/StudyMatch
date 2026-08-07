interface PaginationProps {
  offset: number;
  limit: number;
  total: number;
  onPageChange: (offset: number) => void;
}

export function Pagination({ offset, limit, total, onPageChange }: PaginationProps) {
  if (total <= limit) return null;

  const start = offset + 1;
  const end = Math.min(offset + limit, total);
  const canGoPrev = offset > 0;
  const canGoNext = offset + limit < total;

  return (
    <div className="flex items-center justify-between text-sm text-slate-600">
      <span>
        Showing {start}-{end} of {total}
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!canGoPrev}
          onClick={() => onPageChange(Math.max(0, offset - limit))}
          className="rounded-md border border-slate-200 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={!canGoNext}
          onClick={() => onPageChange(offset + limit)}
          className="rounded-md border border-slate-200 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
