import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The app talks to a relative /api, so dev and any future single-process deployment
// use the same URLs. Here that is proxied to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
