import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { fetchDetail, updateKnowledgeBase } from "@/services/knowledge-base";
import type { UpdateKnowledgeBaseRequest } from "@/types/api";

interface Props {
  kbId: string | null;
  onClose: () => void;
}

// 编辑知识库：打开时拉详情预填；settings 以格式化 JSON 展示，保存前本地 parse。
export function EditKnowledgeBaseDialog({ kbId, onClose }: Props) {
  const queryClient = useQueryClient();
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [settingsText, setSettingsText] = React.useState("{}");
  const [loading, setLoading] = React.useState(false);

  const open = kbId !== null;

  // 打开时拉取详情预填
  React.useEffect(() => {
    if (!kbId) return;
    let cancelled = false;
    setLoading(true);
    fetchDetail(kbId)
      .then((d) => {
        if (cancelled) return;
        setName(d.name);
        setDescription(d.description ?? "");
        setSettingsText(JSON.stringify(d.settings ?? {}, null, 2));
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : "加载详情失败"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [kbId]);

  const mutation = useMutation({
    mutationFn: (body: UpdateKnowledgeBaseRequest) => updateKnowledgeBase(kbId!, body),
    onSuccess: () => {
      toast.success("已保存");
      queryClient.invalidateQueries({ queryKey: ["kb-tree"] });
      onClose();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "保存失败"),
  });

  const onSave = () => {
    let settings: Record<string, unknown>;
    try {
      settings = JSON.parse(settingsText);
    } catch {
      toast.error("settings JSON 格式错误，请检查后再保存");
      return;
    }
    mutation.mutate({ name, description, settings });
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>编辑知识库</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>名称</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} disabled={loading} />
          </div>
          <div className="space-y-1">
            <Label>描述</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={loading}
            />
          </div>
          <div className="space-y-1">
            <Label>settings（JSON，含 synonyms / rewrite_hint）</Label>
            <Textarea
              className="font-mono text-xs min-h-[180px]"
              value={settingsText}
              onChange={(e) => setSettingsText(e.target.value)}
              disabled={loading}
            />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            取消
          </Button>
          <Button onClick={onSave} disabled={loading || mutation.isPending}>
            {mutation.isPending ? "保存中…" : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
