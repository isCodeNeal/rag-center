import axios from "axios";

// 统一走 /api 前缀，由 Vite dev server 代理到后端，规避 CORS。
export const http = axios.create({
  baseURL: "/api",
  timeout: 120000,
  headers: { "Content-Type": "application/json" },
});

// 请求拦截器：有 API_KEY 时自动带上 Bearer 头（本地免鉴权调试可留空）。
http.interceptors.request.use((config) => {
  const key = import.meta.env.API_KEY;
  if (key) {
    config.headers.Authorization = `Bearer ${key}`;
  }
  return config;
});

// 鉴权失败（body.code=20010）的明确提示统一在 unwrap 中给出，避免拦截器与
// 调用方 onError 双重 toast。
