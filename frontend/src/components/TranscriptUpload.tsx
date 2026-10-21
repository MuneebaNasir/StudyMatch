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

  return (
    <div className="flex items-center gap-2 text-xs">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={upload.isPending}
        className="rounded-full border border-line px-3 py-1 text-ink/70 hover:bg-line/40 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {upload.isPending ? "Reading transcript..." : "Upload transcript (optional)"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,image/png,image/jpeg"
        aria-label="Upload transcript"
        className="hidden"
        onChange={handleChange}
      />
      {upload.isError && <span className="text-red-600">Couldn't read this file.</span>}
      {extractionFoundNothing && (
        <span className="text-amber-600">
          Couldn't read this file clearly — try a clearer scan or a different file.
        </span>
      )}
      {upload.isSuccess && !extractionFoundNothing && (
        <span className="text-ink/50">Transcript loaded ✓</span>
      )}
    </div>
  );
}
