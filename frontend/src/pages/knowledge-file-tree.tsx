import * as React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { fetchTree } from "@/services/knowledge-base";
import { fetchAuthMe } from "@/services/auth";
import type { KnowledgeTreeKb } from "@/types/api";

export function KnowledgeFileTreePage() {
  const [keywordInput, setKeywordInput] = React.useState("");
  const [keyword, setKeyword] = React.useState("");
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());

  const authMe = useQuery({ queryKey: ["auth-me"], queryFn: fetchAuthMe });
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["kb-tree", keyword],
    queryFn: () => fetchTree(keyword || undefined),
  });

  // 后端只返回一个 tenant，拍平成知识库列表
  const kbs: KnowledgeTreeKb[] = (data ?? []).flatMap((t) => t.knowledge_bases);

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
              当前租户下的知识库 → 文档，可跳转到上传或检索页。
            </p>
          </div>
          {authMe.data && (
            <div className="flex items-center gap-2">
              <Badge>{authMe.data.tenant_name}</Badge>
              <Badge variant="secondary">{authMe.data.tenant_id}</Badge>
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
            <KbRow key={kb.kb_id} kb={kb} expanded={expanded} onToggle={toggle} onCopy={copyKbId} />
          ))}
        </div>
      </div>
    </div>
  );
}

function KbRow({
  kb,
  expanded,
  onToggle,
  onCopy,
}: {
  kb: KnowledgeTreeKb;
  expanded: Set<string>;
  onToggle: (key: string) => void;
  onCopy: (kbId: string) => void;
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
        </div>
      </div>
      {open && (
        <div className="px-3 pb-2">
          {kb.documents.length === 0 ? (
            <p className="py-2 text-xs text-muted-foreground">暂无成功索引的文档。</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1">文件</th>
                  <th className="py-1">document_id</th>
                  <th className="py-1">chunk 数</th>
                </tr>
              </thead>
              <tbody>
                {kb.documents.map((d) => (
                  <tr key={d.document_id} className="border-t">
                    <td className="py-1">{d.title}</td>
                    <td className="py-1 font-mono text-xs">{d.document_id}</td>
                    <td className="py-1">{d.chunk_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
