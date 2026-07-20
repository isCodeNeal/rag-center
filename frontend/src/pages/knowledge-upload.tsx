import * as React from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CreateKnowledgeBase } from "@/components/create-knowledge-base";
import { UploadDocuments } from "@/components/upload-documents";

export function KnowledgeUploadPage() {
  const [tenantId, setTenantId] = React.useState("tenant_demo");
  const [kbId, setKbId] = React.useState("");

  return (
    <div className="min-h-screen bg-muted/30">
      <div className="container max-w-3xl py-8 space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">RAG 知识库管理</h1>
          <p className="text-sm text-muted-foreground">
            创建知识库并上传文档，用于检索链路的调优测试。
          </p>
        </header>

        <div className="space-y-2 rounded-lg border bg-card p-4">
          <Label htmlFor="tenant-id">tenant_id</Label>
          <Input
            id="tenant-id"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            placeholder="tenant_demo"
          />
          <p className="text-xs text-muted-foreground">
            创建知识库和上传文档都会带上这个 tenant_id。
          </p>
        </div>

        <CreateKnowledgeBase tenantId={tenantId} onCreated={(kb) => setKbId(kb.kb_id)} />

        <UploadDocuments tenantId={tenantId} kbId={kbId} onKbIdChange={setKbId} />
      </div>
    </div>
  );
}
