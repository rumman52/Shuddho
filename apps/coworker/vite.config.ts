import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const repositoryRoot = fileURLToPath(new URL("../..", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@shared": fileURLToPath(new URL("../../shared", import.meta.url)) },
  },
  server: { host: "0.0.0.0", port: 5174, strictPort: true, fs: { allow: [repositoryRoot] } },
  preview: { host: "0.0.0.0", port: 4174, strictPort: true },
  build: { outDir: "dist", emptyOutDir: true },
});
