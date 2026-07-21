import { http, unwrap } from "@/services/client";
import type { ApiResponse, AuthMeData } from "@/types/api";

export function fetchAuthMe(): Promise<AuthMeData> {
  return unwrap(http.get<ApiResponse<AuthMeData>>("/v1/auth/me"));
}
