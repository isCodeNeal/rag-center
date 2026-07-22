import * as React from "react";
import { uploadDocument } from "@/services/document";
import { DocumentStatus } from "@/types/api";
import { fileNameToTitle, isTextFile, readFileAsText } from "@/utils/file";

export type UploadItemStatus =
  | "pending"
  | "uploading"
  | "submitted" // 已提交，后台索引中（异步）
  | "failed"
  | "skipped";

export interface UploadItem {
  // 相对路径（文件夹上传时带层级），用作展示的唯一名字
  path: string;
  fileName: string;
  status: UploadItemStatus;
  chunkCount?: number;
  documentId?: string;
  error?: string;
}

interface UploadArgs {
  kbId: string;
  files: File[];
}

// 从文件对象上取相对路径（文件夹上传时 webkitRelativePath 有值）
function getPath(file: File): string {
  const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath || "";
  return rel || file.name;
}

export function useUploadDocuments() {
  const [items, setItems] = React.useState<UploadItem[]>([]);
  const [isUploading, setIsUploading] = React.useState(false);

  const reset = React.useCallback(() => {
    setItems([]);
    setIsUploading(false);
  }, []);

  const update = React.useCallback((path: string, patch: Partial<UploadItem>) => {
    setItems((prev) => prev.map((it) => (it.path === path ? { ...it, ...patch } : it)));
  }, []);

  const upload = React.useCallback(
    async ({ kbId, files }: UploadArgs) => {
      // 初始化列表
      const initial: UploadItem[] = files.map((f) => ({
        path: getPath(f),
        fileName: f.name,
        status: "pending",
      }));
      setItems(initial);
      setIsUploading(true);

      // 顺序上传：一个一个来，实时反馈每个文件的成功/失败
      for (const file of files) {
        const path = getPath(file);

        if (!isTextFile(file.name)) {
          update(path, { status: "skipped", error: "不支持的文件类型（仅支持文本类文件）" });
          continue;
        }

        update(path, { status: "uploading" });
        try {
          const content = await readFileAsText(file);
          if (!content.trim()) {
            update(path, { status: "failed", error: "文件内容为空" });
            continue;
          }
          const data = await uploadDocument({
            kb_id: kbId,
            title: fileNameToTitle(file.name),
            content,
          });
          // 异步索引：收到 PROCESSING 即视为提交成功，真正索引由后台 Worker 完成。
          if (
            data.status === DocumentStatus.PROCESSING ||
            data.status === DocumentStatus.SUCCESS
          ) {
            update(path, {
              status: "submitted",
              chunkCount: data.chunk_count,
              documentId: data.document_id,
            });
          } else {
            update(path, { status: "failed", error: `后端返回状态 ${data.status}` });
          }
        } catch (e) {
          update(path, { status: "failed", error: e instanceof Error ? e.message : "上传失败" });
        }
      }

      setIsUploading(false);
    },
    [update]
  );

  return { items, isUploading, upload, reset };
}
