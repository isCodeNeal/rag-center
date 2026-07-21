import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useCreateKnowledgeBase } from "@/hooks/use-knowledge-base";
import type { KnowledgeBaseData } from "@/types/api";

const schema = z.object({
  name: z.string().min(1, "请输入知识库名称").max(255),
  description: z.string().max(2000).optional(),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  onCreated: (kb: KnowledgeBaseData) => void;
}

export function CreateKnowledgeBase({ onCreated }: Props) {
  const { mutateAsync, isPending } = useCreateKnowledgeBase();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = React.useCallback(
    async (values: FormValues) => {
      try {
        const kb = await mutateAsync({
          name: values.name,
          description: values.description || undefined,
        });
        toast.success(`知识库创建成功：${kb.name}`);
        reset();
        onCreated(kb);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "创建失败");
      }
    },
    [mutateAsync, onCreated, reset]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>1. 创建知识库</CardTitle>
        <CardDescription>创建成功后会自动填入下方上传区域的 kb_id。</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="kb-name">知识库名称</Label>
            <Input id="kb-name" placeholder="例如：退款政策知识库" {...register("name")} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="kb-desc">描述（可选）</Label>
            <Textarea id="kb-desc" placeholder="用于客服退款问题问答" {...register("description")} />
          </div>
          <Button type="submit" disabled={isPending}>
            {isPending ? "创建中..." : "创建知识库"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
