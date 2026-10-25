import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// The browser calls /api/*; Vite forwards it to the backend (or the mock) on this laptop, so the
// pages and the API share one origin and the backend's localhost-only CORS rule never comes up.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.NAMETAGS_API || "http://127.0.0.1:8000";
  const proxy = {
    "/api": { target, changeOrigin: true, ws: true, rewrite: (path: string) => path.replace(/^\/api/, "") },
  };
  return {
    plugins: [react()],
    server: { port: 5173, proxy },
    preview: { port: 4173, proxy },
  };
});
