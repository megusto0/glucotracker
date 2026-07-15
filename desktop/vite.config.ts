import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// @ts-expect-error process is a nodejs global
const tauriDevHost = process.env.TAURI_DEV_HOST;
const host = tauriDevHost || "127.0.0.1";
// @ts-expect-error process is a nodejs global
const base = process.env.VITE_BASE_PATH || "/";
const basePrefix = base === "/" ? "" : base.replace(/\/$/, "");

// https://vite.dev/config/
export default defineConfig(async () => ({
  base,
  plugins: [
    {
      name: "redirect-unprefixed-nightscout",
      configureServer(server) {
        if (!basePrefix) return;
        server.middlewares.use((request, response, next) => {
          const url = new URL(request.url ?? "/", "http://localhost");
          if (url.pathname !== "/nightscout") {
            next();
            return;
          }
          response.statusCode = 302;
          response.setHeader(
            "Location",
            `${basePrefix}${url.pathname}${url.search}`,
          );
          response.end();
        });
      },
    },
    react(),
    tailwindcss(),
  ],
  test: {
    environment: "jsdom",
    setupFiles: "src/tests/setup.ts",
    globals: true,
    css: true,
  },

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host,
    allowedHosts: ["megusto.duckdns.org"],
    hmr: tauriDevHost
      ? {
          protocol: "ws",
          host: tauriDevHost,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },
}));
