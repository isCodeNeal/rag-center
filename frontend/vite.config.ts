import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 前端请求 /api/* 由 dev server 代理到后端（默认 http://localhost:8000），
// 天然规避后端未配置 CORS 的问题。可通过 VITE_API_TARGET 覆盖后端地址。
export default defineConfig(() => {
  const apiTarget = process.env.VITE_API_TARGET || "http://localhost:8000";
  return {
    plugins: [react()],
    envPrefix: ["VITE_", "API_"],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
