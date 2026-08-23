#!/usr/bin/env node
/**
 * Fail the build when the plugin runtime bundle still reads `process.env`.
 *
 * Vite's library mode deliberately leaves `process.env.NODE_ENV` in place (an
 * app build replaces it) so the consumer can decide. React reads it to pick its
 * dev or prod branch, and the very first read happens during module init — so
 * without the `define` in vite.runtime.config.ts the shipped IIFE throws
 * "ReferenceError: process is not defined" before a single plugin bundle is
 * loaded, and every plugin UI renders blank.
 *
 * The bundle is gitignored and rebuilt on every deploy (`prebuild` →
 * `build:runtime`), so a regression here would ship silently and only show up
 * as an empty page in the browser. This check turns that into a failed build.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const bundlePath = resolve(here, '..', 'public', 'plugin-runtime.js');

const source = readFileSync(bundlePath, 'utf8');
const hits = source.match(/process\.env/g) ?? [];

if (hits.length > 0) {
  console.error(
    `plugin-runtime.js contains ${hits.length} unreplaced \`process.env\` reference(s).\n` +
      'The browser has no `process`, so the runtime throws on load and every plugin UI stays blank.\n' +
      "Fix: keep `define: { 'process.env.NODE_ENV': JSON.stringify('production') }` " +
      'in client/vite.runtime.config.ts.',
  );
  process.exit(1);
}

console.log('plugin-runtime.js: no process.env references');
