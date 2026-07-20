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
    throw new Error(body.msg || `请求失败 (code=${body.code})`);
  }
  return body.data as T;
}

export { http };
