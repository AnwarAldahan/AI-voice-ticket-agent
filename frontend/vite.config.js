import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api/* calls are forwarded to the FastAPI backend, so the browser
// only ever talks to one origin during development.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
