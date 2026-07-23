import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Link } from "react-router-dom";
import { useUploadDocuments, type UploadItem } from "@/hooks/use-upload-documents";
import { isBinaryUploadFile } from "@/utils/file";

interface Props {
  kbId: string;
  onKbIdChange: (v: string) => void;
}

function UploadStatusBadge({ item }: { item: UploadItem }) {
  switch (item.status) {
    case "submitted":
      return <Badge className="bg-blue-500 text-white hover:bg-blue-500/90">已提交</Badge>;
    case "failed":
      return <Badge variant="destructive">失败</Badge>;
    case "skipped":
      return <Badge variant="secondary">跳过</Badge>;
    case "uploading":
      return <Badge>上传中</Badge>;
    default:
      return <Badge variant="outline">等待</Badge>;
  }
}

export function UploadDocuments({ kbId, onKbIdChange }: Props) {
  const { items, isUploading, upload, reset } = useUploadDocuments();
  const [files, setFiles] = React.useState<File[]>([]);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const folderInputRef = React.useRef<HTMLInputElement>(null);

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files ? Array.from(e.target.files) : [];
    setFiles(picked);
    reset();
  };

  const startUpload = async () => {
    if (!kbId.trim()) return toast.error("请先填写 kb_id（可在上方创建知识库）");
    if (files.length === 0) return toast.error("请先选择文件或文件夹");

    await upload({ kbId: kbId.trim(), files });
  };

  const summary = React.useMemo(() => {
    const submitted = items.filter((i) => i.status === "submitted").length;
    const failed = items.filter((i) => i.status === "failed").length;
    const skipped = items.filter((i) => i.status === "skipped").length;
    return { submitted, failed, skipped, total: items.length };
  }, [items]);

  const done = items.length > 0 && !isUploading;

  return (
    <Card>
      <CardHeader>
        <CardTitle>2. 上传文档</CardTitle>
        <CardDescription>
          支持选择多个文件或整个文件夹（顺序逐个提交）。支持 .md / .txt（文本解析）和 .pdf /
          .docx（二进制解析），其余文件会被标记为」跳过」。提交后由后台异步索引，可去列表页查看进度。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="kb-id">kb_id</Label>
          <Input
            id="kb-id"
            placeholder="创建知识库后自动填入，或手动粘贴已有 kb_id"
            value={kbId}
            onChange={(e) => onKbIdChange(e.target.value)}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".md,.txt,.pdf,.docx"
            className="hidden"
            onChange={onPick}
          />
          <input
            ref={folderInputRef}
            type="file"
            multiple
            accept=".md,.txt,.pdf,.docx"
            className="hidden"
            // @ts-expect-error 非标准属性，主流浏览器支持文件夹选择
            webkitdirectory=""
            directory=""
            onChange={onPick}
          />
          <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()}>
            选择文件
          </Button>
          <Button type="button" variant="outline" onClick={() => folderInputRef.current?.click()}>
            选择文件夹
          </Button>
          <Button type="button" onClick={startUpload} disabled={isUploading || files.length === 0}>
            {isUploading ? "上传中..." : `开始上传${files.length ? `（${files.length} 个）` : ""}`}
          </Button>
        </div>

        {files.length > 0 && items.length === 0 && (
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">
              已选择 {files.length} 个文件，点击「开始上传」。
            </p>
            {files.some((f) => isBinaryUploadFile(f)) && (
              <p style={{ color: "#888", fontSize: "0.9em" }}>
                包含 PDF / DOCX 文件，将在后台解析，稍大文件需等待索引完成。
              </p>
            )}
          </div>
        )}

        {items.length > 0 && (
          <div className="space-y-3">
            {done && (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span>共 {summary.total} 个：</span>
                <Badge className="bg-blue-500 text-white hover:bg-blue-500/90">
                  已提交 {summary.submitted}
                </Badge>
                <Badge variant="destructive">失败 {summary.failed}</Badge>
                <Badge variant="secondary">跳过 {summary.skipped}</Badge>
                {summary.submitted > 0 && (
                  <Link
                    to="/knowledge-bases"
                    className="text-primary underline underline-offset-2"
                  >
                    去列表查看进度
                  </Link>
                )}
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[45%]">文件</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>chunk 数</TableHead>
                  <TableHead>说明</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((it) => (
                  <TableRow key={it.path}>
                    <TableCell className="font-mono text-xs">{it.path}</TableCell>
                    <TableCell>
                      <UploadStatusBadge item={it} />
                    </TableCell>
                    <TableCell>{it.chunkCount ?? "-"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{it.error ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
