import { useMutation } from "@tanstack/react-query";

import { postQuery } from "../api/client";
import type { TranscriptContext } from "../types";

export function useQuerySearch() {
  return useMutation({
    mutationFn: (
      { query, offset, transcript }: { query: string; offset: number; transcript?: TranscriptContext | null },
    ) => postQuery(query, offset, 20, transcript ?? null),
  });
}
