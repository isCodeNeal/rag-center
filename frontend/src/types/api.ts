// 后端统一响应外壳：{ code, msg, data }
export interface ApiResponse<T> {
  code: number;
  msg: string;
  data: T | null;
}

export interface KnowledgeBaseData {
  kb_id: string;
  name: string;
  tenant_id: string;
  created_at: string;
}

export interface CreateKnowledgeBaseRequest {
  name: string;
  description?: string;
  tenant_id: string;
}

// 文档索引状态：1=SUCCESS 2=FAILED 3=PROCESSING
export const DocumentStatus = {
  SUCCESS: 1,
  FAILED: 2,
  PROCESSING: 3,
} as const;

export interface UploadDocumentRequest {
  tenant_id: string;
  kb_id: string;
  title: string;
  content: string;
  source_type?: string;
}

export interface UploadDocumentData {
  document_id: string;
  kb_id: string;
  status: number;
  chunk_count: number;
}
