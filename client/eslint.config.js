import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Build output — never lint generated bundles (dist = desktop, dist-pi = Pi build).
  globalIgnores(['dist', 'dist-pi']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // --- Staged ESLint hardening (#210, Stufe 2 von #184) ---
      // This gate is BLOCKING. The rules below are deliberately relaxed so the
      // current tree is green; each is ramped back to `error` in a dedicated
      // follow-up PR. Do NOT silence freshly-introduced errors by adding rules
      // here without discussion — see the linked issues.

      // #245 — 164 violations, real typing work across 100+ files. Kept visible as warn.
      '@typescript-eslint/no-explicit-any': 'warn',
      // #244 — risky to auto-fix (effect deps → infinite-loop risk). Stays warn.
      'react-hooks/exhaustive-deps': 'warn',
      // #244 — Fast-Refresh hygiene; ramped to error in the same follow-up.
      // Preserve allowConstantExport from reactRefresh.configs.vite so a bare
      // severity override doesn't re-introduce constant-export warnings.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // #246 — React Compiler lints (react-hooks v7 "recommended"). Not actionable
      // without a deliberate React Compiler migration; set to off so they don't
      // bury the actionable exhaustive-deps warnings. Reactivated in the migration PR.
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      'react-hooks/immutability': 'off',
      'react-hooks/refs': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/static-components': 'off',

      // Enforced from day one. A leading `_` marks an intentionally-unused binding.
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
      }],
    },
  },
  {
    // Playwright e2e tests are not React. The react-hooks plugin misreads
    // Playwright's `use(...)` fixture callback as the React `use` hook
    // (rules-of-hooks false positives, see #210). Disable hook rules here.
    files: ['tests/e2e/**'],
    rules: {
      'react-hooks/rules-of-hooks': 'off',
      'react-hooks/exhaustive-deps': 'off',
    },
  },
])
