import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const devServerPort = Number(env.VITE_DEV_PORT || "5174");

  if (!Number.isInteger(devServerPort) || devServerPort < 1 || devServerPort > 65535) {
    throw new Error("VITE_DEV_PORT must be an integer between 1 and 65535");
  }

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: devServerPort,
      // Keep the comparison environment stable instead of silently falling back to 5175+.
      strictPort: true,
      proxy: {
        "/api": {
          target: env.VITE_PROXY_TARGET || "http://127.0.0.1:8001",
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
      globals: true,
      exclude: ["tests/e2e/**", "node_modules/**", "dist/**"],
    },
  };
});
