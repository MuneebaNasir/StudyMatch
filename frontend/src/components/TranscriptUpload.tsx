import { type ChangeEvent, useRef } from "react";

import { useTranscriptUpload } from "../hooks/useTranscriptUpload";
import type { TranscriptUploadResponse } from "../types";

interface TranscriptUploadProps {
  onUploaded: (response: TranscriptUploadResponse) => void;
}

export function TranscriptUpload({ onUploaded }: TranscriptUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useTranscriptUpload();

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    upload.mutate(file, { onSuccess: (response) => onUploaded(response) });
  }

  // Extraction can run successfully (HTTP 200) while finding nothing usable
  // in the file -- that's a different situation from a genuine success and
  // must not be presented as "loaded". onUploaded above still fires either
  // way; only the message shown to the user differs.
  const extractionFoundNothing =
    upload.isSuccess && upload.data.extraction_confidence === "low" && upload.data.courses.length === 0;

  const courseCount = upload.data?.courses.length ?? 0;

  return (
    <div className="group flex flex-col gap-3 rounded-3xl border-2 border-dashed border-accent/40 bg-background p-4 transition hover:-translate-y-0.5 hover:border-accent/70 hover:shadow-md sm:flex-row sm:items-center">
      <div
        aria-hidden="true"
        className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-accent-soft text-2xl"
      >
        <span className={`inline-block ${upload.isPending ? "animate-bob" : "animate-wiggle-on-hover"}`}>
          {upload.isPending ? "🐌" : "📜"}
        </span>
        {!upload.isPending && <span className="-ml-1 mt-5 inline-block text-base animate-wiggle-on-hover">🐌</span>}
      </div>
      <div className="flex-1 space-y-1">
        <p className="font-heading text-sm font-bold text-ink">Add your transcript (optional)</p>
        <p className="text-xs text-ink/60">
          Our snail will check your completed coursework against each program's requirements. PDF, PNG
          or JPEG — not saved on our servers.
        </p>
        {upload.isPending && <p className="text-xs text-accent">The snail is reading your transcript…</p>}
        {upload.isError && <p className="text-xs text-red-600">Couldn't read this file. 🥺</p>}
        {extractionFoundNothing && (
          <p className="text-xs text-amber-600">
            Couldn't read this file clearly — try a clearer scan or a different file.
          </p>
        )}
        {upload.isSuccess && !extractionFoundNothing && (
          <p className="text-xs font-medium text-green-700">
            Transcript loaded! 🎉 {courseCount} {courseCount === 1 ? "course" : "courses"} found
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={upload.isPending}
        className="self-start rounded-full bg-accent px-5 py-2 text-sm font-medium text-white shadow-sm transition hover:scale-105 hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100 sm:self-center"
      >
        {upload.isPending ? "Reading..." : upload.isSuccess ? "Choose another file" : "Choose file"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,image/png,image/jpeg"
        aria-label="Upload transcript"
        className="hidden"
        onChange={handleChange}
      />
    </div>
  );
}
