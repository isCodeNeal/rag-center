import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { AppHeader } from "@/components/app-header";
import { CreateKnowledgeBase } from "@/components/create-knowledge-base";
import { UploadDocuments } from "@/components/upload-documents";

export function KnowledgeUploadPage() {
  const [searchParams] = useSearchParams();
  const [kbId, setKbId] = React.useState(() => searchParams.get("kb_id") || "");

  return (
    <div className="min-h-screen bg-muted/30">
      <AppHeader />
      <div className="container max-w-3xl py-8 space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">RAG 知识库管理</h1>
          <p className="text-sm text-muted-foreground">
            创建知识库并上传文档，用于检索链路的调优测试。租户由 API Key 自动识别。
          </p>
        </header>

        <CreateKnowledgeBase onCreated={(kb) => setKbId(kb.kb_id)} />

        <UploadDocuments kbId={kbId} onKbIdChange={setKbId} />
      </div>
    </div>
  );
}
