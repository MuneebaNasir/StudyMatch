import { useQuery } from "@tanstack/react-query";

import { getProgram } from "../api/client";

export function useProgramDetail(programId: number | null) {
  return useQuery({
    queryKey: ["program", programId],
    queryFn: () => getProgram(programId as number),
    enabled: programId !== null,
  });
}
