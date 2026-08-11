import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";

const MASTERS_TEMPLATE = `I am looking for a [Master's] program in [AI, agentic AI, and large language models], taught in [English], with [no tuition fees], near [Berlin].

I have a [Bachelor's degree in Computer Science] with a [3.2 GPA on a 4.0 scale] from [Pakistan], and an [IELTS score of 7.0].`;

const PHD_TEMPLATE = `I am looking for a [PhD] position in [machine learning and natural language processing], taught in [English], with [no tuition fees], near [Munich].

I have a [Master's degree in Computer Science] with a [1.7 grade on the German scale] from [Nigeria], [2 years of research experience in NLP], and an [IELTS score of 7.5].`;

const BACHELORS_TEMPLATE = `I am looking for a [Bachelor's] program in [computer science or data science], taught in [English], with [no tuition fees], near [Hamburg].

I completed [high school / Abitur-equivalent] with a [grade of 85%] in [India], and an [IELTS score of 6.5].`;

interface ChatQueryBoxProps {
  onSubmit: (query: string) => void;
  isPending: boolean;
}

export function ChatQueryBox({ onSubmit, isPending }: ChatQueryBoxProps) {
  const [query, setQuery] = useState(MASTERS_TEMPLATE);
  const [isTyping, setIsTyping] = useState(false);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleChange(event: ChangeEvent<HTMLTextAreaElement>) {
    setQuery(event.target.value);
    setIsTyping(true);
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => setIsTyping(false), 1500);
  }

  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    };
  }, []);

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
      <p className="text-xs text-ink/50">Example query — edit the details below to match your own background.</p>
      <textarea
        value={query}
        onChange={handleChange}
        rows={5}
        className="resize-none rounded-lg border border-line p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
      <p
        className={`pointer-events-none text-xs text-ink/40 transition-opacity duration-300 ${isTyping ? "opacity-100" : "opacity-0"}`}
        aria-hidden="true"
      >
        🐌 typing...
      </p>
      <p className="text-xs font-medium text-ink/50">Want to see more examples?</p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setQuery(PHD_TEMPLATE)}
          className="rounded-full border border-line px-3 py-1 text-xs text-ink/70 hover:bg-line/40"
        >
          PhD example
        </button>
        <button
          type="button"
          onClick={() => setQuery(BACHELORS_TEMPLATE)}
          className="rounded-full border border-line px-3 py-1 text-xs text-ink/70 hover:bg-line/40"
        >
          Bachelor's example
        </button>
      </div>
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
