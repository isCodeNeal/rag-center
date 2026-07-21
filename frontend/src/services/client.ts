import { http } from "@/lib/axios";
import type { ApiResponse } from "@/types/api";

/**
 * 解包后端统一响应外壳 {code, msg, data}。
 * code !== 0 视为业务失败，抛出带 msg 的错误，交给上层捕获。
 */
export async function unwrap<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const res = await promise;
  const body = res.data;
  if (body.code !== 0) {
    // 鉴权失败：给出引导用户检查 .env 的明确文案（单一来源，避免重复提示）。
    if (body.code === 20010) {
      throw new Error("API Key 无效或未配置，请检查 frontend/.env 中的 API_KEY");
    }
    throw new Error(body.msg || `请求失败 (code=${body.code})`);
  }
  return body.data as T;
}

export { http };
