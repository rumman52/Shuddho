import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/",
  plugins: [react()],
  resolve: {
    alias: {
      "@shared": fileURLToPath(new URL("../../shared", import.meta.url))
    }
  },
  build: {
    outDir: "dist"
  },
  server: {
    port: 5173
  }
});

