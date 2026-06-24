import { defineConfig } from 'vite';

// Builds the in-iframe runtime as a single IIFE asset into `public/`, so Vite
// serves it at `/plugin-runtime.js` in BOTH dev (public is served at root) and
// prod (public is copied into dist). host.html references it absolutely.
export default defineConfig({
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
