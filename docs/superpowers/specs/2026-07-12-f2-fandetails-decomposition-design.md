# FanDetails.tsx Zerlegung — Design (F2 / #301)

**Datum:** 2026-07-12
**Issue:** #301 (F2 — Komponenten über 500 Zeilen)
**Komponente:** `client/src/components/fan-control/FanDetails.tsx` (619 Zeilen)

## Ziel

`FanDetails.tsx` verletzt die 500-Zeilen-Konvention der `pages/CLAUDE.md`. Die
Komponente wird **verhaltenserhaltend** in einen schlanken Orchestrator plus
Logik-Hook, pure Helper und reine Präsentations-Subkomponenten zerlegt.

- **Vorher:** 619 Zeilen, ein God-Component (State + 16 Handler + 4 JSX-Blöcke)
- **Nachher:** Orchestrator ~160 Zeilen, alle Units unter der Konvention
- **Kein** Verhaltens-, API- oder Prop-Interface-Wechsel nach außen. Der einzige
  Konsument `pages/FanControl.tsx` und der Barrel `fan-control/index.ts` bleiben
  unverändert (`FanDetails` behält Default-Export + identische Props).

## Ausgangslage

- Konsument: nur `pages/FanControl.tsx` (`import { ..., FanDetails, ... } from '../components/fan-control'`).
- Aktuell **keine** eigenen Tests für `FanDetails` → die Zerlegung bringt netto
  neue Testabdeckung.
- Die 5 Curve-Editor-Varianten (`CurveEditorFlat/Target/Mix/Sync`, `FanCurveChart`)
  sind bereits eigene Komponenten und werden **nicht** angefasst — nur im
  Orchestrator verdrahtet.

## Zielstruktur

```
components/fan-control/
  FanDetails.tsx                    # schlanker Orchestrator (~160 Zeilen)
  fanCurveValidation.ts             # pure: validateCurvePoints(...)
  fan-details/
    FanPresetProfileButtons.tsx     # Header Preset/Profil-Buttons
    FanCurveGraphControls.tsx       # View-Toggle + Save/Discard
    FanCurveTableEditor.tsx         # Tabellen-Editor (Graph-Curve, table view)
    FanStatsGrid.tsx                # Stats-Grid inkl. Hysteresis-Input
    index.ts                        # Barrel
hooks/
  useFanCurveEditor.ts              # gesamter State + Effekte + Handler
```

`fan-control/index.ts` bekommt **keine** neuen öffentlichen Re-Exports — die
`fan-details/*`-Teile und der Hook sind Implementierungsdetails von `FanDetails`
und werden intern relativ importiert.

## Einheiten

### `hooks/useFanCurveEditor.ts` (Logik)

Kapselt die gesamte bisherige Zustandslogik von `FanDetails`:

- **State:** `curvePoints`, `viewMode`, `hysteresis`, `isUpdatingHysteresis`,
  `curveType`, `showMoreProfiles`, `localGpuManualEnabled` + `userEditedRef`.
- **Effekte:** curveType-Sync bei Fan-Wechsel; curvePoints-Sync (nur wenn nicht
  user-editiert); userEditedRef-Reset bei Fan-Wechsel; hysteresis-Sync;
  `onEditingChange`-Benachrichtigung bei `hasUnsavedChanges`.
- **Derivations:** `hasUnsavedChanges` (Memo), `hysteresisChanged`, `canEdit`,
  `systemProfiles`/`userProfiles`.
- **Handler (16):** `handleCurveTypeChange`, `handleFlatChange`,
  `handleTargetChange`, `handleMixChange`, `handleSyncChange`,
  `handleSaveCurve`, `handleDiscardChanges`, `handleAddPoint`,
  `handleRemovePoint`, `handleUpdatePoint`, `handleApplyPreset`,
  `handleApplyProfileCurve`, `handleChartPointsChange`,
  `handleHysteresisChange`, `handleHysteresisSave`, `handleAdvancedChange`.

**Signatur (Skizze):**

```ts
function useFanCurveEditor(
  fan: FanInfo,
  opts: {
    isReadOnly: boolean;
    onCurveUpdate: (fanId: string, points: FanCurvePoint[]) => void;
    onConfigUpdate?: () => void;
    onEditingChange?: (isEditing: boolean) => void;
    onApplyProfile?: (profile: FanCurveProfile) => void;
    profiles?: FanCurveProfile[];
  }
): { /* state + derivations + handlers */ }
```

Der Hook nutzt `useTranslation` intern (für Toast-/Fehlermeldungen), damit die
Handler-Semantik 1:1 erhalten bleibt.

### `fanCurveValidation.ts` (pure Helper)

`validateCurvePoints` wird aus der Komponente herausgezogen und pure gemacht —
min/max-PWM und die `t`-Funktion werden als Parameter übergeben statt aus dem
Closure gelesen:

```ts
export function validateCurvePoints(
  points: FanCurvePoint[],
  bounds: { minPwm: number; maxPwm: number },
  t: TFunction
): { valid: boolean; error?: string }
```

Regeln unverändert: min. 2 Punkte, strikt aufsteigende Temperaturen,
PWM innerhalb `[minPwm, maxPwm]`.

### Präsentations-Subkomponenten (`fan-details/*`)

Alle rein präsentational — Props rein, Callbacks raus, kein eigener Server-State,
keine API-Aufrufe. i18n via `useTranslation(['system','common'])` wie gehabt.

- **`FanPresetProfileButtons`** — System-Profile (oder Fallback-Presets
  silent/balanced/performance) + User-Profile-Dropdown. Props: `systemProfiles`,
  `userProfiles`, `showMoreProfiles`, `onToggleMore`, `onApplyPreset`,
  `onApplyProfile`.
- **`FanCurveGraphControls`** — Configure-Info-Text, Chart/Table-View-Toggle,
  Save/Discard-Buttons (nur bei `hasUnsavedChanges && !isReadOnly`). Props:
  `viewMode`, `onViewModeChange`, `hasUnsavedChanges`, `isReadOnly`, `onSave`,
  `onDiscard`.
- **`FanCurveTableEditor`** — Tabelle mit editierbaren temp/pwm-Feldern,
  Remove-Buttons, Add-Point-Button. Props: `curvePoints`, `canEdit`,
  `minPwm`/`maxPwm`, `onUpdatePoint`, `onRemovePoint`, `onAddPoint`.
- **`FanStatsGrid`** — Min/Max-PWM, Emergency-Temp, Sensor-ID + editierbares
  Hysteresis-Feld (mit unsaved/saving-Indikatoren). Props: `fan`, `canEdit`,
  `hysteresis`, `isUpdatingHysteresis`, `hysteresisChanged`,
  `onHysteresisChange`, `onHysteresisSave`.

### `FanDetails.tsx` (Orchestrator)

- Ruft `useFanCurveEditor`, destrukturiert State + Handler.
- Rendert Header + `FanPresetProfileButtons`, den `CurveTypeSelector`, die
  bedingte Curve-Editor-Auswahl (graph → `FanCurveGraphControls` +
  `FanCurveChart`/`FanCurveTableEditor`; flat/target/mix/sync → jeweiliger
  Editor), `AdvancedFanSettings`, bedingt `GpuManualModeToggle`, und
  `FanStatsGrid`.
- Enthält **keine** Zustandslogik mehr, nur Composition + Layout-Wrapper.

## Bewusst außerhalb Scope (Nebenbefund)

`localGpuManualEnabled` (bisher `FanDetails.tsx:36`) ist reiner lokaler UI-State
ohne Server-Sync und wird bei Fan-Wechsel **nicht** zurückgesetzt — ein latenter
Mini-Bug. Er wird **verhaltensgleich** in den Hook übernommen (kein Fix in
diesem Refactor). Wird separat als Nebenbefund festgehalten.

## Test-Strategie (T7-konform)

Aktuell 0 Tests für `FanDetails` → die Zerlegung ist ein Netto-Zugewinn.

- **`fanCurveValidation.test.ts`** — alle Validierungszweige (min-points,
  ascending-temp-Verletzung, PWM-unter-min / -über-max, valid case).
- **`useFanCurveEditor.test.ts`** — `hasUnsavedChanges`-Detektion,
  add/remove/update-point (inkl. Min-2-Guard beim Remove),
  preset/profile-apply, save (validierungsblockiert bei ungültiger Kurve) /
  discard, userEdited-Guard verhindert Server-Sync-Überschreiben,
  Reset bei Fan-Wechsel.
- **Subkomponenten** — je ein leichter Render-/Interaktions-Test
  (Buttons feuern Callbacks, read-only rendert keine Editier-Controls).

## Verifikation vor PR

- `npx vitest run` (Frontend-Suite grün, neue Tests inklusive).
- `npx eslint .` (0-Error-Gate).
- `npm run build` (tsc -b über app/node/test Projekte).
- Whole-Branch-Review (Multi-Agent) am Ende.
- `components/CLAUDE.md`-Eintrag für `fan-control/` um die `fan-details/*`-Zerlegung
  ergänzen.
