import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { retrieve } from "@/services/rag";
import { HelpTooltip } from "@/components/help-tooltip";
import type {
  RetrieveMode,
  RetrieveRequest,
  RetrievedChunk,
  RetrieveData,
  QueryProcessingMetadata,
} from "@/types/api";

const MODES: RetrieveMode[] = ["vector", "bm25", "hybrid"];

// 100px 右对齐的标签 + 同行控件
function Field({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-[100px] shrink-0 text-right text-sm text-muted-foreground">{label}</span>
      <div className="flex flex-1 items-center gap-2">
        {children}
        {help && <HelpTooltip text={help} />}
      </div>
    </div>
  );
}

export function RetrievePage() {
  const [searchParams] = useSearchParams();
  const [kbId, setKbId] = React.useState(() => searchParams.get("kb_id") || "");
  const [query, setQuery] = React.useState("");
  const [configOpen, setConfigOpen] = React.useState(true);

  const [topK, setTopK] = React.useState(5);
  const [mode, setMode] = React.useState<RetrieveMode>("hybrid");
  const [vectorTopK, setVectorTopK] = React.useState(20);
  const [bm25TopK, setBm25TopK] = React.useState(20);
  const [rrfK, setRrfK] = React.useState(60);
  const [rerankEnabled, setRerankEnabled] = React.useState(true);
  const [rerankTopN, setRerankTopN] = React.useState(5);
  const [rewriteEnabled, setRewriteEnabled] = React.useState(false);

  const mutation = useMutation<RetrieveData, Error, RetrieveRequest>({
    mutationFn: retrieve,
    onError: (e) => toast.error(e.message),
  });

  const onSubmit = () => {
    if (!kbId.trim()) return toast.error("请填写 kb_id");
    if (!query.trim()) return toast.error("请填写 query");

    const payload: RetrieveRequest = {
      kb_id: kbId.trim(),
      user_id: "debug_user",
      query: query.trim(),
      top_k: topK,
      retrieval_options: {
        mode,
        ...(mode === "hybrid"
          ? { vector_top_k: vectorTopK, bm25_top_k: bm25TopK, rrf_k: rrfK }
          : {}),
      },
      ...(rerankEnabled ? { rerank_options: { enabled: true, top_n: rerankTopN } } : {}),
      ...(rewriteEnabled ? { query_options: { enabled: true, strategy: "rewrite" } } : {}),
    };
    mutation.mutate(payload);
  };

  const result = mutation.data;

  return (
    <div className="min-h-screen bg-muted/30">
      <AppHeader />
      <div className="container max-w-3xl space-y-6 py-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">检索调试</h1>
          <p className="text-sm text-muted-foreground">输入 query 直接查看召回结果与评分明细。</p>
        </header>

        {/* Card 1: 检索配置 */}
        <Card>
          <CardHeader className="cursor-pointer" onClick={() => setConfigOpen((v) => !v)}>
            <CardTitle className="flex items-center gap-2 text-base">
              <span>{configOpen ? "▾" : "▶"}</span> 检索配置
            </CardTitle>
          </CardHeader>
          {configOpen && (
            <CardContent className="space-y-4">
              <div className="space-y-3 rounded-md border bg-muted/40 p-3">
                <Field label="kb_id">
                  <Input value={kbId} onChange={(e) => setKbId(e.target.value)} />
                </Field>
              </div>

              <Field label="top_k" help="召回候选数量。启用 rerank 时建议大于 rerank top_n。">
                <Input
                  type="number"
                  className="w-28"
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                />
              </Field>

              <Field label="检索模式" help="vector=纯向量语义；bm25=纯关键词；hybrid=两者并行后 RRF 融合。">
                {MODES.map((m) => (
                  <Button
                    key={m}
                    type="button"
                    size="sm"
                    variant={mode === m ? "default" : "outline"}
                    onClick={() => setMode(m)}
                  >
                    {m}
                  </Button>
                ))}
              </Field>

              {mode === "hybrid" && (
                <Field label="hybrid 参数" help="vector_top_k/bm25_top_k 为两路各自召回数量；rrf_k 为 RRF 融合平滑系数，越大越弱化排名靠前项的权重。">
                  <label className="text-xs text-muted-foreground">vector_top_k</label>
                  <Input
                    type="number"
                    className="w-20"
                    value={vectorTopK}
                    onChange={(e) => setVectorTopK(Number(e.target.value))}
                  />
                  <label className="text-xs text-muted-foreground">bm25_top_k</label>
                  <Input
                    type="number"
                    className="w-20"
                    value={bm25TopK}
                    onChange={(e) => setBm25TopK(Number(e.target.value))}
                  />
                  <label className="text-xs text-muted-foreground">rrf_k</label>
                  <Input
                    type="number"
                    className="w-20"
                    value={rrfK}
                    onChange={(e) => setRrfK(Number(e.target.value))}
                  />
                </Field>
              )}

              <Field label="rerank" help="用大模型对候选做精排，top_n 为精排后最终返回条数。">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={rerankEnabled}
                    onChange={(e) => setRerankEnabled(e.target.checked)}
                  />
                  启用
                </label>
                {rerankEnabled && (
                  <>
                    <label className="text-xs text-muted-foreground">top_n</label>
                    <Input
                      type="number"
                      className="w-20"
                      value={rerankTopN}
                      onChange={(e) => setRerankTopN(Number(e.target.value))}
                    />
                  </>
                )}
              </Field>

              <Field
                label="query 改写"
                help="用 AI 把口语问题改成更好搜的说法；更慢、消耗 LLM，可对比开关效果。"
              >
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={rewriteEnabled}
                    onChange={(e) => setRewriteEnabled(e.target.checked)}
                  />
                  启用 query 改写
                </label>
              </Field>
            </CardContent>
          )}
        </Card>

        {/* Card 2: 检索与召回 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">检索与召回</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              rows={3}
              placeholder="输入 query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Button onClick={onSubmit} disabled={mutation.isPending}>
              {mutation.isPending ? "检索中…" : "检索"}
            </Button>

            {result && (
              <div className="space-y-3">
                <div className="text-sm text-muted-foreground">召回结果</div>
                {result.retrieved_chunks.map((c, i) => (
                  <ChunkCard key={c.chunk_id} rank={i + 1} chunk={c} />
                ))}
                {result.retrieved_chunks.length === 0 && (
                  <p className="text-sm text-muted-foreground">无召回结果。</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Card 3: 运行摘要 */}
        {result && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">运行摘要</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <div>
                mode={result.metadata.retrieval.mode} | top_k={result.metadata.top_k} | 服务端耗时{" "}
                {result.metadata.latency_ms}ms
              </div>
              <div className="text-muted-foreground">
                vector:{result.metadata.retrieval.vector_count ?? "—"} bm25:
                {result.metadata.retrieval.bm25_count ?? "—"} fused:
                {result.metadata.retrieval.fused_count ?? "—"}
              </div>
              <div className="text-muted-foreground">
                rerank: {result.metadata.rerank.enabled ? "启用" : "关闭"}
                {result.metadata.rerank.model ? ` / ${result.metadata.rerank.model}` : ""}
                {result.metadata.retrieval.degraded ? " | ⚠ hybrid degraded" : ""}
                {result.metadata.rerank.degraded ? " | ⚠ rerank degraded" : ""}
              </div>
              {result.metadata.query_processing && (
                <QueryProcessingSummary qp={result.metadata.query_processing} />
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function ChunkCard({ rank, chunk }: { rank: number; chunk: RetrievedChunk }) {
  const [open, setOpen] = React.useState(false);
  const fmt = (v?: number | null) => (v === null || v === undefined ? "—" : v.toFixed(2));
  return (
    <div className="rounded-md border bg-background p-3 text-sm">
      <div className="font-mono text-xs">
        #{rank} score={fmt(chunk.score)} vector={fmt(chunk.vector_score)} bm25=
        {fmt(chunk.bm25_score)} rerank={fmt(chunk.rerank_score)}
      </div>
      <div className="mt-1 text-muted-foreground">
        {chunk.title} / {chunk.document_id} / {chunk.chunk_id}
      </div>
      <button
        type="button"
        className="mt-1 text-xs text-primary"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "收起内容" : "展开内容"}
      </button>
      {open && <p className="mt-1 whitespace-pre-wrap">{chunk.content}</p>}
    </div>
  );
}

function QueryProcessingSummary({ qp }: { qp: QueryProcessingMetadata }) {
  const rewritten = qp.effective_query !== qp.raw_query;
  const expanded = qp.search_query !== qp.effective_query;
  return (
    <div className="mt-2 space-y-1 border-t pt-2 text-muted-foreground">
      <div>原话：{qp.raw_query}</div>
      {rewritten && <div>实际检索句：{qp.effective_query}</div>}
      {expanded && (
        <div className="text-foreground">最终检索句：{qp.search_query}</div>
      )}
      {qp.rewrite_latency_ms != null && <div>改写耗时 {qp.rewrite_latency_ms}ms</div>}
      {qp.degraded && (
        <div className="text-amber-600">
          ⚠ 改写失败，已用原话检索{qp.degraded_reason ? `（${qp.degraded_reason}）` : ""}
        </div>
      )}
      {qp.synonym_applied && qp.synonym_expansions.length > 0 && (
        <div>词表扩展：{qp.synonym_expansions.join("、")}</div>
      )}
    </div>
  );
}
