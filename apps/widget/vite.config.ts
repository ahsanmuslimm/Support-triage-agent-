import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

export default defineConfig({
  plugins: [preact()],
  build: {
    lib: {
      entry: "src/embed.tsx",
      name: "TriageWidget",
      formats: ["iife"],
      fileName: () => "widget.js",
    },
    cssCodeSplit: false,
    outDir: "dist",
  },
});
