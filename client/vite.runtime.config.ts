import { defineConfig } from 'vite';

// Builds the in-iframe runtime as a single IIFE asset into `public/`, so Vite
// serves it at `/plugin-runtime.js` in BOTH dev (public is served at root) and
// prod (public is copied into dist). host.html references it absolutely.
export default defineConfig({
  // Library mode does not replace `process.env.NODE_ENV` the way an app build
  // does, and React reads it during module init. Without this the IIFE throws
  // "process is not defined" in the browser and every plugin UI stays blank.
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    emptyOutDir: false,
    outDir: 'public',
    lib: {
      entry: 'src/plugin-runtime/index.ts',
      name: 'BaluHostPluginRuntime',
      formats: ['iife'],
      fileName: () => 'plugin-runtime.js',
    },
    rollupOptions: {
      output: {
        entryFileNames: 'plugin-runtime.js',
        assetFileNames: (info) =>
          info.name && info.name.endsWith('.css') ? 'plugin-runtime.css' : '[name][extname]',
      },
    },
  },
});
