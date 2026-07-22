import { http, unwrap } from "@/services/client";
import type { ApiResponse, FeedbackData, FeedbackRequest, RetrieveData, RetrieveRequest } from "@/types/api";

export function retrieve(payload: RetrieveRequest): Promise<RetrieveData> {
  return unwrap(http.post<ApiResponse<RetrieveData>>("/v1/rag/retrieve", payload));
}

export function submitFeedback(payload: FeedbackRequest): Promise<FeedbackData> {
  return unwrap(http.post<ApiResponse<FeedbackData>>("/v1/rag/feedback", payload));
}
