import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The browser calls /api/... and Vite forwards to the FastAPI backend (no CORS needed).
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";
// In Docker on Windows, file change events do not cross the bind mount: poll instead.
const usePolling = process.env.VITE_USE_POLLING === "true";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
