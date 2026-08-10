/// <reference types="vitest/config" />
import { resolve } from "node:path";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import babel from "@rolldown/plugin-babel";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import { defineConfig } from "vite";
import * as os from "node:os";

const isDebug = !!process.env.TAURI_ENV_DEBUG;
const host = process.env.TAURI_DEV_HOST;

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [
        tanstackRouter({
            target: "react",
        }),
        react(),
        babel({
            presets: [reactCompilerPreset()],
        }),
    ],
    server: {
        port: 1420,
        strictPort: true,
        host: host || false,
        hmr: host
            ? {
                  protocol: "ws",
                  host,
                  port: 1421,
              }
            : undefined,
        watch: {
            ignored: ["**/src-tauri/**"],
        },
    },
    build: {
        minify: isDebug ? false : "esbuild",
        sourcemap: isDebug ? "inline" : false,
        target: process.env.TAURI_ENV_PLATFORM == "windows" ? "chrome105" : "safari13",
    },
    resolve: {
        alias: [{ find: "@", replacement: resolve(__dirname, "./src") }],
    },
    test: {
        environment: "jsdom",
        // FU-16 (2026-08-10): setup file polyfills window.matchMedia
        // (jsdom doesn't implement it; Mantine's color-scheme provider
        // calls it during render). Without this polyfill, every test
        // that renders a Mantine component throws "TypeError:
        // window.matchMedia is not a function". See src/test/setup.ts
        // for details.
        setupFiles: ["./src/test/setup.ts"],
    },
    define: {
        "import.meta.env.VITE_PLATFORM": JSON.stringify(os.platform()),
    },
});
