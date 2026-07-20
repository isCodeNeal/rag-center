import { http, unwrap } from "@/services/client";
import type {
  ApiResponse,
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
