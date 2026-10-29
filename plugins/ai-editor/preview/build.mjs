// Bundles the preview page (app.tsx) and the review page's live player (live.tsx). preview.py copies this folder's
// .tsx files and this file into ~/.ai-video-editor/remotion/preview/ and runs it there, so they use the renderer's own
// node_modules and the same src/ the render does. Output: dist/app.js, dist/live.js.
import * as esbuild from "esbuild";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
await esbuild.build({
  entryPoints: [path.join(here, "app.tsx"), path.join(here, "live.tsx")],
  outdir: path.join(here, "dist"),
  bundle: true,
  format: "esm",
  splitting: true,   // the 1,500 Google fonts look.tsx can load become chunks fetched on use, not 27 MB up front
  chunkNames: "chunks/[name]-[hash]",
  target: "es2020",
  jsx: "automatic",
  minify: true,
  define: { "process.env.NODE_ENV": '"production"' },
  logLevel: "warning",
  plugins: [{
    name: "preview-sfx",
    setup(b) {
      // src/StyleEdit.tsx's "./Sfx" -> ./Sfx.tsx here (see that file)
      b.onResolve({ filter: /^\.\/Sfx$/ }, (a) =>
        path.basename(a.resolveDir) === "src" ? { path: path.join(here, "Sfx.tsx") } : undefined);
    },
  }],
});
