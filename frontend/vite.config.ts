import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build : l'app est servie par FastAPI sous /react/.
// Dev (npm run dev) : on proxifie /api vers le serveur Python (python -m interface).
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/react/" : "/",
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1200 }, // MapLibre pèse à lui seul ~800 ko
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
}));
