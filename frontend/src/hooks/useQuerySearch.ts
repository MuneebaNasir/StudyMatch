import { useMutation } from "@tanstack/react-query";

import { postQuery } from "../api/client";

export function useQuerySearch() {
  return useMutation({
    mutationFn: ({ query, offset, sessionToken }: { query: string; offset: number; sessionToken?: string | null }) =>
      postQuery(query, offset, 20, sessionToken ?? null),
  });
}
