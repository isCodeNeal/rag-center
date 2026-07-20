import axios from "axios";

// 统一走 /api 前缀，由 Vite dev server 代理到后端，规避 CORS。
export const http = axios.create({
  baseURL: "/api",
  timeout: 120000,
  headers: { "Content-Type": "application/json" },
});
