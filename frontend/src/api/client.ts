import type { ProgramDetail, QueryResponse, SearchFilters, SearchResponse } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function postQuery(query: string, offset = 0, limit = 20): Promise<QueryResponse> {
  return request<QueryResponse>("/query", {
    method: "POST",
    body: JSON.stringify({ query, offset, limit }),
  });
}

export function postSearch(
  filters: SearchFilters, semanticQuery: string | null, offset = 0, limit = 20,
): Promise<SearchResponse> {
  return request<SearchResponse>("/search", {
    method: "POST",
    body: JSON.stringify({ filters, semantic_query: semanticQuery, offset, limit }),
  });
}

export function getProgram(id: number): Promise<ProgramDetail> {
  return request<ProgramDetail>(`/programs/${id}`);
}
