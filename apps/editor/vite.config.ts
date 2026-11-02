import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const repositoryRoot = fileURLToPath(new URL("../..", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@shared": fileURLToPath(new URL("../../shared", import.meta.url)) },
  },
  server: {
    host: "0.0.0.0",
    fs: { allow: [repositoryRoot] },
    proxy: {
      "/backend": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: path => path.replace(/^\/backend/, ""),
      },
    },
  },
  preview: { host: "0.0.0.0" },
  build: { outDir: "dist", emptyOutDir: true },
});
