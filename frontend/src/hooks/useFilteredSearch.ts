import { useMutation } from "@tanstack/react-query";

import { postSearch } from "../api/client";
import type { SearchFilters } from "../types";

export function useFilteredSearch() {
  return useMutation({
    mutationFn: ({ filters, semanticQuery }: { filters: SearchFilters; semanticQuery: string | null }) =>
      postSearch(filters, semanticQuery),
  });
}
