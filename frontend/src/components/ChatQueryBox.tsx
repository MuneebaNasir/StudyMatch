import { type FormEvent, useState } from "react";

interface ChatQueryBoxProps {
  onSubmit: (query: string) => void;
  isPending: boolean;
}

export function ChatQueryBox({ onSubmit, isPending }: ChatQueryBoxProps) {
  const [query, setQuery] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-2xl border border-line bg-background p-4 shadow-sm"
    >
      <textarea
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Describe your background and what you're looking for..."
        rows={3}
        className="resize-none rounded-lg border border-line p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
      <button
        type="submit"
        disabled={isPending || query.trim().length === 0}
        className="self-end rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isPending ? "Reading your profile and checking eligibility..." : "Search programs"}
      </button>
    </form>
  );
}
