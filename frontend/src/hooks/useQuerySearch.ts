import { useMutation } from "@tanstack/react-query";

import { postQuery } from "../api/client";

export function useQuerySearch() {
  return useMutation({
    mutationFn: (query: string) => postQuery(query),
  });
}
