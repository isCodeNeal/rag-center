import { http, unwrap } from "@/services/client";
import type { ApiResponse, RetrieveData, RetrieveRequest } from "@/types/api";

export function retrieve(payload: RetrieveRequest): Promise<RetrieveData> {
  return unwrap(http.post<ApiResponse<RetrieveData>>("/v1/rag/retrieve", payload));
}
