import { useMutation } from "@tanstack/react-query";

import { postTranscript } from "../api/client";

export function useTranscriptUpload() {
  return useMutation({
    mutationFn: (file: File) => postTranscript(file),
  });
}
