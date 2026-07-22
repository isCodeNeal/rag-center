import { http, unwrap } from "@/services/client";
import type {
  ApiResponse,
  CreateKnowledgeBaseRequest,
  KnowledgeBaseData,
  KnowledgeBaseDetailData,
  KnowledgeTreeTenant,
  UpdateKnowledgeBaseRequest,
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

export function fetchDetail(kbId: string): Promise<KnowledgeBaseDetailData> {
  return unwrap(
    http.get<ApiResponse<KnowledgeBaseDetailData>>(
      `/v1/knowledge-bases/${encodeURIComponent(kbId)}`
    )
  );
}

export function updateKnowledgeBase(
  kbId: string,
  body: UpdateKnowledgeBaseRequest
): Promise<KnowledgeBaseDetailData> {
  return unwrap(
    http.patch<ApiResponse<KnowledgeBaseDetailData>>(
      `/v1/knowledge-bases/${encodeURIComponent(kbId)}`,
      body
    )
  );
}

export function deleteKnowledgeBase(kbId: string): Promise<null> {
  return unwrap(
    http.delete<ApiResponse<null>>(`/v1/knowledge-bases/${encodeURIComponent(kbId)}`)
  );
}
