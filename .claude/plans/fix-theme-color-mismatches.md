# Fix: Fehlende Farbstufen nach Theme-Variable-Refactoring

## Context

Das Frontend-Refactoring hat hardcoded Tailwind-Slate-Farben durch Theme-CSS-Variablen ersetzt. Dabei wurden mehrere Graustufen auf zu wenige Theme-Variablen gemappt. Das Ergebnis: Im Dark Mode sind manche Texte zu hell und manche Hintergründe zu dunkel, weil die Zwischenstufen fehlen.

**Kernproblem**: Das Theme-System hat 3 Text-Stufen (primary/secondary/tertiary = slate-100/300/400), aber der ursprüngliche Code nutzte 6+ Stufen (white, slate-100, 200, 300, 400, 500, 600). Besonders slate-500 (369 Instanzen!) wurde fälschlich auf slate-400 gemappt.

## Änderungen

### 1. Neue Theme-Variable `--color-text-muted` hinzufügen

**Dateien:** `client/src/index.css` (`:root`), `client/src/contexts/ThemeContext.tsx` (alle 6 Themes), `client/tailwind.config.js`

Neue Variable für die "gedämpfte Text"-Stufe zwischen tertiary und Hintergrund:

| Theme | Wert | Entspricht |
|---|---|---|
| dark | `100, 116, 139` | slate-500 |
| light | `148, 163, 184` | slate-400 |
| ocean | `2, 132, 199` | sky-600 |
| forest | `34, 197, 94` | green-500 |
| sunset | `251, 113, 133` | rose-400 |
| midnight | `124, 58, 237` | violet-600 |

Tailwind-Token: `text-theme-text-muted` → `rgb(var(--color-text-muted) / <alpha-value>)`

### 2. Neue Theme-Variable `--color-bg-interactive` hinzufügen

Für Toggle-Tracks, Hover-States und Badges die vorher `bg-slate-600` waren:

| Theme | Wert | Entspricht |
|---|---|---|
| dark | `71, 85, 105` | slate-600 |
| light | `203, 213, 225` | slate-300 |
| ocean | `7, 89, 133` | sky-800 |
| forest | `77, 124, 15` | lime-700 |
| sunset | `159, 18, 57` | rose-800 |
| midnight | `91, 33, 182` | violet-800 |

Tailwind-Token: `bg-theme-bg-interactive` → `rgb(var(--color-bg-interactive) / <alpha-value>)`

### 3. Falsche Mappings korrigieren (4 Kategorien)

#### 3a. `text-theme-text-tertiary` → `text-theme-text-muted` (ehem. text-slate-500)
- **369 Instanzen in 67 Dateien**
- Methode: `git diff HEAD` analysieren, alle Zeilen finden wo `text-slate-500` zu `text-theme-text-tertiary` wurde, und durch `text-theme-text-muted` ersetzen

#### 3b. `text-theme-text` → `text-white` auf farbigen Hintergründen
- **25 Instanzen in 14 Dateien**
- Reines Weiß ist nötig für Kontrast auf farbigen Buttons (bg-sky-500, bg-emerald-600, bg-red-600 etc.)
- Betroffene Dateien: FanCard, FanDetails, PresetEditor, MaintenancePanel, SchedulerConfigModal, ServiceCard, SchedulerDashboard, SettingsPage, NetworkWidget, PluginsPanel, ServicesPanel, LanguageSettings, MaintenanceTools, BenchmarkProgress

#### 3c. `text-theme-text-tertiary` / `text-theme-border-secondary` → `text-theme-text-muted` (ehem. text-slate-600)
- **23 Instanzen in ~9 Dateien** (11x als text-tertiary, 12x als border-secondary)
- Für diese sehr gedämpften Elemente (Separatoren, dim Icons): `text-theme-text-muted/70` approximiert slate-600 gut
- Betroffene: ColumnFilterPanel, ActivityFeed, ConnectedDevicesWidget, ServiceSummaryWidget, FileManager, SharesPage

#### 3d. `bg-theme-bg-tertiary` → `bg-theme-bg-interactive` (ehem. bg-slate-600)
- **26 Instanzen in 14 Dateien** (4 base + 16 hover + 6 mixed)
- Betroffene: NetworkWidget, DynamicModeSection, RateLimitsTab, FanCard, FanDetails, PresetEditor, SchedulerCard, ServicesStatusTab, ServicesTab, PowerTab

## Betroffene Dateien

| Datei | Änderung |
|---|---|
| `client/src/index.css` | `:root`-Defaults: `--color-text-muted` + `--color-bg-interactive` |
| `client/src/contexts/ThemeContext.tsx` | 2 neue Variablen in allen 6 Themes |
| `client/tailwind.config.js` | 2 neue Tailwind-Tokens |
| 67+ Komponentendateien | Klassen-Ersetzungen (3a-3d) |

## Implementierungsreihenfolge

1. Theme-Infrastruktur: `index.css` → `ThemeContext.tsx` → `tailwind.config.js`
2. Bulk-Fix 3a: text-slate-500 Mappings (369x) — per `git diff` identifizieren und ersetzen
3. Fix 3b: text-white Revert auf farbigen Buttons (25x)
4. Fix 3c: text-slate-600 Mappings (23x)
5. Fix 3d: bg-slate-600 Mappings (26x)

## Verifizierung

1. `npm run build` — Kompiliert fehlerfrei
2. Dark Mode: Gedämpfter Text (Labels, Hints) ist wieder dunkler als vorher
3. Farbige Buttons: Weißer Text gut lesbar
4. Toggles/Hovers: Sichtbar gegen den dunklen Hintergrund
5. Alle 6 Themes durchklicken — kein visueller Bruch
