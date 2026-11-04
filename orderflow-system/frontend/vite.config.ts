import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Dev only: read OFX_API_KEY from ../backend/.env (or the environment) and attach it to proxied requests,
 *  so the key stays on this machine and never enters the browser bundle. */
function apiKey(): string {
  if (process.env.OFX_API_KEY) return process.env.OFX_API_KEY;
  const f = resolve(__dirname, "../backend/.env");
  if (!existsSync(f)) return "";
  for (const line of readFileSync(f, "utf8").split(/\r?\n/)) {
    const m = /^\s*OFX_API_KEY\s*=\s*(.*)$/.exec(line);
    if (m) return m[1]!.trim().replace(/^['"]|['"]$/g, "");
  }
  return "";
}

const key = apiKey();
const headers = key ? { "x-api-key": key } : undefined;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", headers },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true, headers },
    },
  },
});
