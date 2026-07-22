import { http, unwrap } from "@/services/client";
import type {
  ApiResponse,
  DocumentStatusData,
  UploadDocumentData,
  UploadDocumentRequest,
} from "@/types/api";

export function uploadDocument(
  payload: UploadDocumentRequest
): Promise<UploadDocumentData> {
  return unwrap(
    http.post<ApiResponse<UploadDocumentData>>("/v1/documents/upload", payload)
  );
}

export function deleteDocument(documentId: string): Promise<null> {
  return unwrap(
    http.delete<ApiResponse<null>>(`/v1/documents/${encodeURIComponent(documentId)}`)
  );
}

export function reindexDocument(documentId: string): Promise<DocumentStatusData> {
  return unwrap(
    http.post<ApiResponse<DocumentStatusData>>(
      `/v1/documents/${encodeURIComponent(documentId)}/reindex`
    )
  );
}
