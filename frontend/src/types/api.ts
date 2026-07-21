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
}

// 文档索引状态：1=SUCCESS 2=FAILED 3=PROCESSING
export const DocumentStatus = {
  SUCCESS: 1,
  FAILED: 2,
  PROCESSING: 3,
} as const;

export interface UploadDocumentRequest {
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

// ---- 知识库树形 ----
export interface KnowledgeTreeDoc {
  document_id: string;
  title: string;
  status: number;
  chunk_count: number;
  created_at: string;
}

export interface KnowledgeTreeKb {
  kb_id: string;
  name: string;
  description?: string | null;
  created_at: string;
  documents: KnowledgeTreeDoc[];
}

export interface KnowledgeTreeTenant {
  tenant_id: string;
  knowledge_bases: KnowledgeTreeKb[];
}

// ---- 检索 ----
export type RetrieveMode = "vector" | "bm25" | "hybrid";

export interface RetrieveRequest {
  kb_id: string;
  user_id: string;
  query: string;
  top_k?: number;
  retrieval_options?: {
    mode?: RetrieveMode;
    vector_top_k?: number;
    bm25_top_k?: number;
    rrf_k?: number;
  };
  rerank_options?: {
    enabled?: boolean;
    top_n?: number;
  };
}

export interface RetrievedChunk {
  document_id: string;
  chunk_id: string;
  title: string;
  content: string;
  score: number;
  vector_score?: number | null;
  bm25_score?: number | null;
  vector_rank?: number | null;
  bm25_rank?: number | null;
  retrieval_source?: string | null;
  rerank_score?: number | null;
}

export interface RetrievalMetadata {
  mode: string;
  fusion?: string | null;
  rrf_k?: number | null;
  vector_store?: string | null;
  keyword_search?: string | null;
  vector_top_k?: number | null;
  bm25_top_k?: number | null;
  vector_count?: number | null;
  bm25_count?: number | null;
  fused_count?: number | null;
  degraded: boolean;
  degraded_reason?: string | null;
}

export interface RerankMetadata {
  enabled: boolean;
  provider?: string | null;
  llm_provider?: string | null;
  model?: string | null;
  top_n?: number | null;
  candidate_count?: number | null;
  degraded: boolean;
  error?: string | null;
}

export interface RetrieveMetadata {
  top_k: number;
  vector_store: string;
  latency_ms: number;
  retrieval: RetrievalMetadata;
  rerank: RerankMetadata;
}

export interface RetrieveData {
  query: string;
  kb_id: string;
  retrieved_chunks: RetrievedChunk[];
  metadata: RetrieveMetadata;
}

export interface AuthMeData {
  tenant_id: string;
  tenant_name: string;
  key_prefix: string;
  key_name: string;
}
