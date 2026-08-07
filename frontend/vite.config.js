import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run build` emits into dist/, which main.py mounts at / — so the
// production app is one uvicorn process. `npm run dev` is only for iterating on
// the UI, and proxies /api to that same backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
