import { http, unwrap } from "@/services/client";
import type {
  ApiResponse,
  CreateKnowledgeBaseRequest,
  KnowledgeBaseData,
  KnowledgeTreeTenant,
} from "@/types/api";

export function createKnowledgeBase(
  payload: CreateKnowledgeBaseRequest
): Promise<KnowledgeBaseData> {
  return unwrap(
    http.post<ApiResponse<KnowledgeBaseData>>("/v1/knowledge-bases/create", payload)
  );
}

export function fetchTree(keyword?: string): Promise<KnowledgeTreeTenant[]> {
  return unwrap(
    http.get<ApiResponse<KnowledgeTreeTenant[]>>("/v1/knowledge-bases/tree", {
      params: keyword ? { keyword } : undefined,
    })
  );
}
