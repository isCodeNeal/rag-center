import * as React from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/status-badge";
import { PlanBadge } from "@/components/plan-badge";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EditKnowledgeBaseDialog } from "@/components/edit-knowledge-base-dialog";
import { fetchTree, deleteKnowledgeBase } from "@/services/knowledge-base";
import { deleteDocument, reindexDocument } from "@/services/document";
import { fetchAuthMe } from "@/services/auth";
import { DocumentStatus, type KnowledgeTreeDoc, type KnowledgeTreeKb } from "@/types/api";

export function KnowledgeFileTreePage() {
  const queryClient = useQueryClient();
  const [keywordInput, setKeywordInput] = React.useState("");
  const [keyword, setKeyword] = React.useState("");
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());
  const [editKbId, setEditKbId] = React.useState<string | null>(null);
  const [deleteKb, setDeleteKb] = React.useState<KnowledgeTreeKb | null>(null);
  const [deleteDoc, setDeleteDoc] = React.useState<KnowledgeTreeDoc | null>(null);

  const authMe = useQuery({ queryKey: ["auth-me"], queryFn: fetchAuthMe });
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["kb-tree", keyword],
    queryFn: () => fetchTree(keyword || undefined),
    // 存在 PROCESSING 文档时每 3s 轮询，全部进入终态后停止。
    refetchInterval: (query) => {
      const tenants = query.state.data ?? [];
      const hasProcessing = tenants.some((t) =>
        t.knowledge_bases.some((kb) =>
          kb.documents.some((d) => d.status === DocumentStatus.PROCESSING)
        )
      );
      return hasProcessing ? 3000 : false;
    },
  });

  const kbs: KnowledgeTreeKb[] = (data ?? []).flatMap((t) => t.knowledge_bases);
  const hasProcessing = kbs.some((kb) =>
    kb.documents.some((d) => d.status === DocumentStatus.PROCESSING)
  );

  const refetchTree = () => queryClient.invalidateQueries({ queryKey: ["kb-tree"] });

  const reindexMutation = useMutation({
    mutationFn: (documentId: string) => reindexDocument(documentId),
    onSuccess: () => {
      toast.success("已重新提交索引");
      refetchTree();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "重试失败"),
  });

  const deleteDocMutation = useMutation({
    mutationFn: (documentId: string) => deleteDocument(documentId),
    onSuccess: () => {
      toast.success("文档已删除");
      setDeleteDoc(null);
      refetchTree();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "删除失败"),
  });

  const deleteKbMutation = useMutation({
    mutationFn: (kbId: string) => deleteKnowledgeBase(kbId),
    onSuccess: () => {
      toast.success("知识库已删除");
      setDeleteKb(null);
      refetchTree();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "删除失败"),
  });

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const copyKbId = async (kbId: string) => {
    try {
      await navigator.clipboard.writeText(kbId);
      toast.success("已复制 kb_id");
    } catch {
      toast.error("复制失败");
    }
  };

  return (
    <div className="min-h-screen bg-muted/30">
      <AppHeader />
      <div className="container max-w-5xl py-8 space-y-6">
        <header className="flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight">知识库列表</h1>
            <p className="text-sm text-muted-foreground">
              当前租户下的知识库 → 文档；可编辑、删除、重试索引。
            </p>
          </div>
          {authMe.data && (
            <div className="flex items-center gap-2">
              <PlanBadge plan={authMe.data.plan} />
              <Badge>{authMe.data.tenant_name}</Badge>
              <Badge variant="secondary">{authMe.data.tenant_id}</Badge>
              <span className="text-xs text-muted-foreground">
                今日检索 {authMe.data.usage.retrieve_daily_count} /{" "}
                {authMe.data.limits.retrieve_daily}
              </span>
            </div>
          )}
        </header>

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setKeyword(keywordInput.trim());
          }}
        >
          <Input
            placeholder="按知识库名称模糊搜索"
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
          />
          <Button type="submit">搜索</Button>
        </form>

        {hasProcessing && (
          <p className="text-xs text-blue-600">有文档正在索引…（每 3 秒自动刷新）</p>
        )}
        {isLoading && <p className="text-sm text-muted-foreground">加载中…</p>}
        {isError && (
          <p className="text-sm text-destructive">
            加载失败：{(error as Error)?.message ?? "未知错误"}
          </p>
        )}
        {data && kbs.length === 0 && (
          <p className="text-sm text-muted-foreground">没有匹配的知识库。</p>
        )}

        <div className="space-y-2">
          {kbs.map((kb) => (
            <KbRow
              key={kb.kb_id}
              kb={kb}
              expanded={expanded}
              onToggle={toggle}
              onCopy={copyKbId}
              onEdit={() => setEditKbId(kb.kb_id)}
              onDelete={() => setDeleteKb(kb)}
              onReindexDoc={(id) => reindexMutation.mutate(id)}
              onDeleteDoc={(doc) => setDeleteDoc(doc)}
            />
          ))}
        </div>
      </div>

      <EditKnowledgeBaseDialog kbId={editKbId} onClose={() => setEditKbId(null)} />

      <ConfirmDialog
        open={deleteKb !== null}
        onOpenChange={(v) => !v && setDeleteKb(null)}
        title="删除知识库"
        description={`将删除「${deleteKb?.name ?? ""}」及其全部文档，不可恢复。`}
        confirmText="删除"
        loading={deleteKbMutation.isPending}
        onConfirm={() => deleteKb && deleteKbMutation.mutate(deleteKb.kb_id)}
      />

      <ConfirmDialog
        open={deleteDoc !== null}
        onOpenChange={(v) => !v && setDeleteDoc(null)}
        title="删除文档"
        description={`将删除文档「${deleteDoc?.title ?? ""}」及其全部 chunk，不可恢复。`}
        confirmText="删除"
        loading={deleteDocMutation.isPending}
        onConfirm={() => deleteDoc && deleteDocMutation.mutate(deleteDoc.document_id)}
      />
    </div>
  );
}

function KbRow({
  kb,
  expanded,
  onToggle,
  onCopy,
  onEdit,
  onDelete,
  onReindexDoc,
  onDeleteDoc,
}: {
  kb: KnowledgeTreeKb;
  expanded: Set<string>;
  onToggle: (key: string) => void;
  onCopy: (kbId: string) => void;
  onEdit: () => void;
  onDelete: () => void;
  onReindexDoc: (documentId: string) => void;
  onDeleteDoc: (doc: KnowledgeTreeDoc) => void;
}) {
  const key = `k:${kb.kb_id}`;
  const open = expanded.has(key);
  const query = `kb_id=${encodeURIComponent(kb.kb_id)}`;
  return (
    <div className="rounded-md border bg-background">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          className="flex flex-1 items-center gap-2 text-left"
          onClick={() => onToggle(key)}
        >
          <span className="w-3 text-muted-foreground">{open ? "▾" : "▶"}</span>
          <span className="font-medium">{kb.name}</span>
          <span className="font-mono text-xs text-muted-foreground">
            kb_id: {kb.kb_id.slice(0, 8)}…
          </span>
          <span className="text-xs text-muted-foreground">
            （{kb.documents.length} 个文档）
          </span>
        </button>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" variant="outline" onClick={() => onCopy(kb.kb_id)}>
            复制 kb_id
          </Button>
          <Button size="sm" variant="outline" asChild>
            <Link to={`/?${query}`}>去上传</Link>
          </Button>
          <Button size="sm" variant="outline" asChild>
            <Link to={`/retrieve?${query}`}>去检索</Link>
          </Button>
          <Button size="sm" variant="outline" onClick={onEdit}>
            编辑
          </Button>
          <Button size="sm" variant="destructive" onClick={onDelete}>
            删除库
          </Button>
        </div>
      </div>
      {open && (
        <div className="px-3 pb-2">
          {kb.documents.length === 0 ? (
            <p className="py-2 text-xs text-muted-foreground">暂无文档。</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1">文件</th>
                  <th className="py-1">document_id</th>
                  <th className="py-1">状态</th>
                  <th className="py-1">chunk 数</th>
                  <th className="py-1">操作</th>
                </tr>
              </thead>
              <tbody>
                {kb.documents.map((d) => (
                  <DocRow
                    key={d.document_id}
                    doc={d}
                    onReindex={() => onReindexDoc(d.document_id)}
                    onDelete={() => onDeleteDoc(d)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function DocRow({
  doc,
  onReindex,
  onDelete,
}: {
  doc: KnowledgeTreeDoc;
  onReindex: () => void;
  onDelete: () => void;
}) {
  const isProcessing = doc.status === DocumentStatus.PROCESSING;
  const isFailed = doc.status === DocumentStatus.FAILED;
  return (
    <tr className="border-t align-top">
      <td className="py-1">{doc.title}</td>
      <td className="py-1 font-mono text-xs">{doc.document_id}</td>
      <td className="py-1">
        <div className="flex flex-col gap-0.5">
          <StatusBadge status={doc.status} />
          {isFailed && doc.error_message && (
            <span
              className="max-w-[200px] truncate text-xs text-destructive"
              title={doc.error_message}
            >
              {doc.error_message}
            </span>
          )}
        </div>
      </td>
      <td className="py-1">{doc.chunk_count}</td>
      <td className="py-1">
        <div className="flex gap-2">
          {isFailed && (
            <Button size="sm" variant="outline" onClick={onReindex}>
              重试
            </Button>
          )}
          {!isProcessing && (
            <Button size="sm" variant="outline" onClick={onDelete}>
              删除
            </Button>
          )}
        </div>
      </td>
    </tr>
  );
}
