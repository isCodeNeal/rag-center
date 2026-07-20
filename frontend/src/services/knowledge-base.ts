import { http, unwrap } from "@/services/client";
import type {
  ApiResponse,
  CreateKnowledgeBaseRequest,
  KnowledgeBaseData,
} from "@/types/api";

export function createKnowledgeBase(
  payload: CreateKnowledgeBaseRequest
): Promise<KnowledgeBaseData> {
  return unwrap(
    http.post<ApiResponse<KnowledgeBaseData>>("/v1/knowledge-bases/create", payload)
  );
}
