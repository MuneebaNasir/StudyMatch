import { useMutation } from "@tanstack/react-query";

import { postSearch } from "../api/client";
import type { SearchFilters } from "../types";

export function useFilteredSearch() {
  return useMutation({
    mutationFn: (
      { filters, semanticQuery, offset }: { filters: SearchFilters; semanticQuery: string | null; offset: number },
    ) => postSearch(filters, semanticQuery, offset),
  });
}
