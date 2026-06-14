# ESLint-Gate in CI scharf schalten — Design

**Datum:** 2026-06-14
**Issue:** #210 (Folgearbeit aus #184, Stufe 2: *ESLint im CI durchsetzen*)
**Branch:** `feat/ci-eslint-gate`
**Status:** Design genehmigt

## Problem

`client/eslint.config.js` (Flat-Config) und das `lint`-Script existieren, werden
aber von **keinem** Workflow aufgerufen. `npx eslint .` ist aktuell nicht grün:

```
343 Probleme (291 Errors, 52 Warnings) über 138 Dateien
```

Verifiziert am 2026-06-14 (lokal, `client/`): Zahlen decken sich exakt mit dem
Issue. Verteilung nach Regel:

| Regel | Errors | Warnings |
|---|---:|---:|
| `@typescript-eslint/no-explicit-any` | 164 | 0 |
| `react-hooks/exhaustive-deps` | 0 | 52 |
| `react-hooks/set-state-in-effect` | 35 | 0 |
| `@typescript-eslint/no-unused-vars` | 32 | 0 |
| `react-refresh/only-export-components` | 14 | 0 |
| `no-useless-catch` | 11 | 0 |
| `react-hooks/preserve-manual-memoization` | 9 | 0 |
| `no-empty` | 7 | 0 |
| `react-hooks/immutability` | 6 | 0 |
| `react-hooks/refs` | 5 | 0 |
| `react-hooks/rules-of-hooks` | 4 | 0 |
| `react-hooks/purity` | 2 | 0 |
| `react-hooks/static-components` | 1 | 0 |
| `prefer-const` | 1 | 0 |

### Korrektur zum Issue: die 4 `rules-of-hooks`-Treffer sind keine Bugs

Das Issue vermutet bei `react-hooks/rules-of-hooks` (×4) „potenziell echte Bugs".
Die Untersuchung am 2026-06-14 zeigt: **alle 4 sind False-Positives.** Sie liegen
ausschließlich in `client/tests/e2e/fixtures/auth.fixture.ts` (Zeilen 144, 157,
171, 189) und betreffen **Playwrights `use(page)`-Fixture-Callback**, nicht
Reacts `use`-Hook. Das react-hooks-Plugin verwechselt das Playwright-`use` mit dem
gleichnamigen React-Hook. Es gibt keinen einzigen `rules-of-hooks`-Treffer in
`src/`.

## Scope

Dieser Branch ist **PR A — „Gate scharf schalten"**. Er etabliert einen
blockierenden ESLint-Step im CI auf einer kuratierten Config, die den Ist-Zustand
grün macht, und fixt dabei die billigen, korrekten High-Value-Errors.

**Bewusst NICHT in diesem Branch** (Roadmap als Folge-PRs, siehe unten):
- Hochstufung `@typescript-eslint/no-explicit-any` → `error` (164 Verstöße, echte
  Typ-Arbeit über 100+ Dateien) → **PR C**.
- Reaktivierung der React-Compiler-Lints im Zuge einer bewussten React-Compiler-
  Migration → **PR C**.
- `react-refresh/only-export-components` (14) und `exhaustive-deps`-Abbau → **PR B**.

## Design

### 1. Kuratierte `client/eslint.config.js`

Ergänzung um Override-Sektionen mit dokumentiertem Kommentarblock (Verweis auf
#210, „gestaffelt"). Rule-Mapping:

**Bleiben/werden `error` — Verstöße in diesem PR gefixt:**

| Regel | Verstöße | Fix-Strategie |
|---|---:|---|
| `prefer-const` | 1 | `let` → `const` |
| `no-empty` | 7 | Leere Blöcke füllen/entfernen bzw. intentional kommentieren |
| `@typescript-eslint/no-unused-vars` | 32 | Entfernen oder `^_`-Prefix (Ignore-Pattern in Config) |
| `no-useless-catch` | 11 | Redundante `try { … } catch (e) { throw e }` auspacken |

Für `no-unused-vars` wird die Regel mit
`{ argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }`
konfiguriert, damit absichtlich ungenutzte Bindings per `_`-Prefix sauber
markierbar sind.

**Werden `warn` (sichtbar, Ramp-Ziel späterer PRs):**

| Regel | Verstöße | Ramp-Ziel |
|---|---:|---|
| `@typescript-eslint/no-explicit-any` | 164 | PR C → `error` |
| `react-hooks/exhaustive-deps` | 52 | PR B (bleibt vorerst `warn` — riskant) |
| `react-refresh/only-export-components` | 14 | PR B → `error` |

**Werden `off` (React-Compiler-Lints aus `react-hooks` v7 recommended):**

| Regel | Verstöße |
|---|---:|
| `react-hooks/set-state-in-effect` | 35 |
| `react-hooks/preserve-manual-memoization` | 9 |
| `react-hooks/immutability` | 6 |
| `react-hooks/refs` | 5 |
| `react-hooks/purity` | 2 |
| `react-hooks/static-components` | 1 |

Begründung `off` statt `warn`: Diese ~58 Treffer sind ohne React-Compiler-Migration
nicht handlungsfähig. Auf `warn` würden sie die echten, später handlungsfähigen
`exhaustive-deps`-Warnungen zumüllen. Reaktivierung erfolgt bewusst in PR C.

### 2. e2e-Ausnahme (löst die 4 `rules-of-hooks`-False-Positives)

Separater Config-Block für `tests/e2e/**`, der **alle `react-hooks/*`-Regeln auf
`off`** setzt — Playwright-Fixtures sind kein React. Damit verschwinden die 4
False-Positives, ohne `rules-of-hooks` global zu schwächen: die Regel bleibt
überall sonst `error` (und ist dort bereits grün, da es keine `src/`-Treffer gibt).

### 3. CI-Step in `.github/workflows/ci-check.yml`

Neuer blockierender Step im `frontend-build`-Job, nach `npm ci` und vor `Build`
(fail-fast):

```yaml
- name: Lint (ESLint)
  working-directory: client
  run: npx eslint .
```

Läuft auf `ubuntu-latest` — kein self-hosted Runner berührt, keine der vier
CI/CD-Security-Layer betroffen. `.github/workflows/` ist CODEOWNERS-owned →
Review durch Xveyn (Layer 1, advisory auf `main`, erwartet).

### 4. Verifikation

Lint-Fixes sind kein Logik-Feature; klassisches TDD greift nicht. Die
Akzeptanzbedingung ist:

1. `cd client && npx eslint .` → **exit 0** (0 Errors; Warnings erlaubt)
2. `cd client && npm run build` → grün (keine TS-Regression durch Fixes)
3. `cd client && npx vitest run` → grün (keine Verhaltensregression)

Alle drei lokal grün, bevor der PR geöffnet wird.

## Roadmap (Folge-PRs, dokumentiert, nicht Teil dieses Branches)

- **PR B:** `react-refresh/only-export-components` (14) fixen → `error`;
  `exhaustive-deps` (52) gezielt abbauen (vorsichtig, Endlosschleifen-Risiko).
- **PR C:** `no-explicit-any` (164) schrittweise abbauen → Regel auf `error`;
  React-Compiler-Lints im Zuge der React-Compiler-Migration reaktivieren.

## Risiken & Trade-offs

- **`no-useless-catch`-Fix:** Beim Auspacken redundanter try/catch sicherstellen,
  dass der `catch`-Block wirklich nur rethrowt (kein Logging/Mapping). ESLint
  feuert die Regel nur bei reinem Rethrow — Risiko minimal, aber pro Fundstelle
  prüfen.
- **`no-unused-vars`-Fix:** Beim Entfernen ungenutzter Imports/Variablen darauf
  achten, keine Test-Monkeypatch-Targets oder Side-Effect-Imports zu killen
  (vgl. Backend-Ruff-Erfahrung). Im Zweifel `_`-Prefix statt Entfernen.
- **CRLF:** Repo läuft mit `core.autocrlf=true` auf Windows — Edits müssen die
  vorhandene Zeilenende-Konvention der jeweiligen Datei beibehalten.
- **Build/Vitest-Regression:** Jede Code-Änderung wird durch Build + Vitest
  abgesichert (Schritt 4), bevor der PR rausgeht.
