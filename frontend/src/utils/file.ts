// 仅支持按文本读取的扩展名；其余文件（PDF、docx、图片等）直接判失败，
// 因为后端 /documents/upload 接收的是纯文本 content，二进制读成文本会变乱码。
export const TEXT_EXTENSIONS = [
  ".txt",
  ".md",
  ".markdown",
  ".csv",
  ".json",
  ".log",
  ".text",
] as const;

export function getExtension(filename: string): string {
  const idx = filename.lastIndexOf(".");
  return idx >= 0 ? filename.slice(idx).toLowerCase() : "";
}

export function isTextFile(filename: string): boolean {
  return TEXT_EXTENSIONS.includes(getExtension(filename) as (typeof TEXT_EXTENSIONS)[number]);
}

// 支持的文本文件（可 readAsText → JSON upload）
export function isTextUploadFile(file: File): boolean {
  const ext = getExtension(file.name);
  return ext === ".md" || ext === ".txt";
}

// 支持的二进制文件（走 FormData multipart upload）
export function isBinaryUploadFile(file: File): boolean {
  const ext = getExtension(file.name);
  return ext === ".pdf" || ext === ".docx";
}

// 所有支持的上传格式
export function isSupportedUploadFile(file: File): boolean {
  return isTextUploadFile(file) || isBinaryUploadFile(file);
}

/** 用 FileReader 把文件读成 UTF-8 文本。 */
export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error("文件读取失败"));
    reader.readAsText(file, "utf-8");
  });
}

/** 去掉扩展名作为文档标题；空则回退为原文件名。 */
export function fileNameToTitle(filename: string): string {
  const idx = filename.lastIndexOf(".");
  const base = idx > 0 ? filename.slice(0, idx) : filename;
  return base || filename;
}
