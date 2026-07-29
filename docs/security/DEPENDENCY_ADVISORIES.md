# Advisory-Register: bewusst nicht gefixte Meldungen

Begründungen zu Dependabot- und Code-Scanning-Meldungen, die **absichtlich** nicht
durch ein Update geschlossen werden — weil sie uns nicht treffen, weil der Fix
teurer wäre als das Risiko, oder weil er blockiert ist.

## Wofür das hier ist — und wofür nicht

GitHub hält den **Zustand** (offen / dismissed / fixed). Diese Datei hält die
**Begründung**. Beides getrennt zu führen hat einen konkreten Anlass: das
`dismissed_comment`-Feld der Dependabot-API ist auf **280 Zeichen** begrenzt.
Eine Begründung, die Fundstellen im Code nennt und sagt, wann sie ungültig wird,
passt dort nicht hinein. In der UI ist sie außerdem nicht diffbar, taucht in
keinem Review auf und ist weg, sobald der Alert neu aufgemacht wird.

**Keine zweite Wahrheit über den Zustand.** Ob ein Alert offen ist, steht in
GitHub, nicht hier. Wenn diese Datei und GitHub sich widersprechen, gewinnt
GitHub — und der Eintrag hier gehört korrigiert.

## Die Regel, die das Register vor dem Verrotten schützt

> **Jeder Eintrag braucht eine Re-Evaluierungsbedingung.**

Also einen überprüfbaren Satz, der beschreibt, wann die Entscheidung *aufhört zu
gelten*. „Betrifft uns nicht" ohne diese Bedingung ist kein Befund, sondern eine
Ausrede mit unbegrenzter Haltbarkeit — und genau die Sorte Notiz, die drei Jahre
später niemand mehr anzufassen wagt.

Ein Eintrag ohne Re-Evaluierungsbedingung ist unvollständig und soll im Review
zurückgewiesen werden.

## Status-Werte

| Status | Bedeutung |
|---|---|
| `nicht zutreffend` | Der verwundbare Codepfad existiert bei uns nicht. In GitHub als `not_used` dismissed. |
| `aufgeschoben` | Trifft uns, der Fix ist aber unverhältnismäßig teuer. Bleibt offen und sichtbar. |
| `blockiert` | Fix ist gewollt, scheitert aktuell an etwas Externem (Toolchain, Major-Upgrade). |

---

## GHSA-qwww-vcr4-c8h2 — React Router: RSC Mode CSRF Bypass

| | |
|---|---|
| **Status** | `nicht zutreffend` |
| **Entschieden** | 2026-07-29 |
| **Paket** | `react-router` (transitiv über `react-router-dom`) |
| **Betroffen** | `>= 7.12.0, < 8.3.0` — wir fahren 7.18.2 |
| **Alert** | Dependabot #76, dismissed als `not_used` |

**Warum wir nicht betroffen sind.** Die Advisory beschreibt einen CSRF-Bypass im
**RSC-Modus** von React Router. BaluHost ist ein reiner Client-SPA:

- `client/src/App.tsx:1` importiert `BrowserRouter` aus `react-router-dom` — der
  deklarative Client-Router, kein Data-Router und kein Framework-Modus
- kein einziges `@react-router/*`-Serverpaket ist installiert (weder
  `@react-router/serve` noch `@react-router/express`)
- kein SSR, kein RSC — der Build ist ein statisches Vite-Bundle, das Nginx ausliefert

Der verwundbare Codepfad wird also nie erreicht.

**Was der Fix kosten würde.** React Router **8.3.0** — ein Major. Für eine
Advisory, die einen Modus betrifft, den wir nicht fahren, ist das der falsche
Tausch: Major-Risiko gegen Null-Nutzen.

> **Re-Evaluierungsbedingung.** Diese Einschätzung fällt, sobald **eines** davon
> zutrifft:
> 1. ein `@react-router/*`-Paket taucht in `client/package.json` auf,
> 2. `client/src/App.tsx` wechselt von `BrowserRouter` auf `createBrowserRouter`
>    mit Framework-/RSC-Modus, oder
> 3. das Frontend bekommt überhaupt Server-Rendering.
>
> Dann ist der Alert neu zu bewerten und der Major fällig.

---

## brace-expansion — DoS über unbegrenzte Expansion (OOM)

| | |
|---|---|
| **Status** | `aufgeschoben` |
| **Entschieden** | 2026-07-29 |
| **Paket** | `brace-expansion`, transitiv über `minimatch` → `eslint` / `typescript-eslint` |
| **Betroffen** | `<= 5.0.7` — also **jede** existierende Version, auch die neueste |
| **Quelle** | nur `npm audit`, kein GitHub-Alert |

**Warum aufgeschoben.** Die Advisory hat noch keine gefixte Version: der Bereich
deckt alles bis einschließlich der aktuellen 5.0.7 ab. npms einziger
Auflösungspfad ist `eslint@10.x` — ein Major der gesamten Lint-Toolchain.

Die Exposition ist gering: `brace-expansion` läuft ausschließlich zur Lint-Zeit
über Glob-Muster, die **wir** in der ESLint-Konfiguration schreiben. Es
verarbeitet keine Nutzereingaben und wird nicht ausgeliefert.

**Was der Fix kosten würde.** ESLint 9 → 10 mit Konfigurationsanpassung, gegen
einen CI-Gate, der auf `eslint .` mit **0 Errors** steht. Also ein eigener PR mit
echtem Aufwand — nicht Teil eines Dependency-Bündels.

> **Re-Evaluierungsbedingung.** Sobald `brace-expansion` eine gefixte Version
> veröffentlicht, die innerhalb unserer bestehenden Ranges erreichbar ist, wird
> das ein normaler Bump. Unabhängig davon fällig, wenn ESLint 10 aus anderen
> Gründen ansteht — dann fällt das hier als Nebeneffekt mit ab.

---

## quinn-proto / glib — Tauri-Companion (Cargo)

| | |
|---|---|
| **Status** | `blockiert` |
| **Festgehalten** | 2026-07-29 |
| **Paket** | `quinn-proto` 0.11.14 → 0.11.15, `glib` 0.18.5 → 0.20.0 |
| **Ort** | `client/src-tauri/Cargo.lock` |
| **Alerts** | Dependabot, offen |

**Warum noch offen.** Zwei verschiedene Gründe, die nicht zusammengehören:

- **`quinn-proto`** wäre ein reiner Patch (0.11.14 → 0.11.15) und damit
  unkritisch. Er scheitert nur daran, dass auf der Entwicklungsmaschine keine
  Rust-Toolchain installiert ist — ein `Cargo.lock` lässt sich ohne `cargo` weder
  sauber erzeugen noch verifizieren.
- **`glib`** ist etwas anderes: 0.18.5 → 0.20.0 sind **zwei Majors**, und die
  Version hängt an den GTK-Abhängigkeiten von Tauri selbst. Das ist realistisch
  kein Lockfile-Bump, sondern ein Tauri-Upgrade.

Beide betreffen ausschließlich die Companion-App, nicht das Web-Frontend und
nicht das Backend.

> **Re-Evaluierungsbedingung.** `quinn-proto` fällt, sobald irgendjemand mit
> Rust-Toolchain (oder ein CI-Job auf Basis von `tauri-build.yml`) den Bump
> ausführen kann. `glib` fällt zusammen mit dem nächsten Tauri-Upgrade — bis
> dahin nicht einzeln anfassen.

---

## Einen Eintrag ergänzen

1. Meldung in GitHub dismissen (falls zutreffend) mit **Kurz**-Begründung und
   Verweis auf diese Datei — 280 Zeichen sind das Limit.
2. Hier einen Abschnitt nach obigem Muster anlegen: Kennung als Überschrift,
   Status-Tabelle, Begründung mit **Fundstellen im Code** (`datei.ts:zeile`),
   Kosten des Fixes.
3. Die Re-Evaluierungsbedingung schreiben. Ohne sie ist der Eintrag nicht fertig.
4. Wird eine Meldung später doch gefixt, den Abschnitt **löschen** statt ihn
   umzuschreiben — die Historie steht im Git-Log, und ein Register, das auch
   erledigte Fälle sammelt, wird unlesbar.

## Hinweis zur Einsprachigkeit

`docs/security/` führt sonst `.de.md`/`.en.md`-Paare. Diese Datei bewusst nicht:
sie wird bei jedem Dismiss fortgeschrieben, und ein Eintrag, der nur in einer der
beiden Sprachfassungen landet, wäre schlimmer als eine einsprachige Datei — bei
einem Sicherheitsregister ist Auseinanderlaufen der teuerste Fehlermodus.
