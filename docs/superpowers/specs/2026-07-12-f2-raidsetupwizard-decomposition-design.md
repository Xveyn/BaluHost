# RaidSetupWizard.tsx Zerlegung — Design (F2 / #301)

**Datum:** 2026-07-12
**Issue:** #301 (F2 — Komponenten über 500 Zeilen)
**Komponente:** `client/src/components/RaidSetupWizard.tsx` (547 Zeilen)

## Ziel

`RaidSetupWizard.tsx` verletzt die 500-Zeilen-Konvention. Es ist ein 3-Schritt-
Wizard-Modal (Disk-Auswahl → RAID-Level → Bestätigung) — reine State-/JSX-Struktur
ohne DOM-/Interaktions-Subtilitäten. Zerlegung **verhaltenserhaltend**:

- **Vorher:** 547 Zeilen — Datenkonstante + State/Helfer + 4 Render-Funktionen + Modal-Shell.
- **Nachher:** Orchestrator ~80 Zeilen; alle Units unter der Konvention.
- **Kein** Verhaltens- oder Prop-Interface-Wechsel. Öffentliche `RaidSetupWizardProps`
  und Default-Export bleiben. Konsument `pages/RaidManagement.tsx` (einziger, via
  `import RaidSetupWizard from '../components/RaidSetupWizard'`) bleibt unberührt.

## Ausgangslage

- Konsument: nur `pages/RaidManagement.tsx`.
- Kein Barrel (Top-Level-Komponente, Default-Import).
- Aktuell **keine** eigenen Tests → die Zerlegung bringt netto neue Testabdeckung
  (insbesondere die puren Helfer).
- Ein separater `components/raid/`-Ordner existiert bereits (RAID-Status/Disk-Details) —
  die Wizard-Teile kommen in einen **eigenen** `components/raid-setup/`-Ordner
  (konsistent mit dem F2-Muster: jede Zerlegung erhält ihren eigenen Feature-Ordner).

## Zielstruktur

```
components/
  RaidSetupWizard.tsx              # Orchestrator: Modal-Shell + Step-Switch (~80 Zeilen)
  raid-setup/
    raidLevels.ts                  # RAID_LEVELS-Daten + RaidLevelInfo-Typ
    raidWizardHelpers.ts           # PURE: calculateArrayCapacity + isValidArrayName
    RaidWizardStepIndicator.tsx    # Fortschritts-Anzeige
    RaidDiskSelectionStep.tsx      # Schritt 1 (Disk-Auswahl)
    RaidLevelSelectionStep.tsx     # Schritt 2 (RAID-Level)
    RaidConfirmationStep.tsx       # Schritt 3 (Bestätigung + Form)
    index.ts                       # interner Barrel
hooks/
  useRaidSetupWizard.ts            # State + Navigation + Handler
```

`raid-setup/*` und der Hook sind Implementierungsdetails von `RaidSetupWizard` —
kein öffentlicher Re-Export außerhalb.

## Einheiten

### `raid-setup/raidLevels.ts` (Daten)

Die `RAID_LEVELS`-Konstante (5 Einträge) + `RaidLevelInfo`-Typ, 1:1 aus dem Original.
Enthält die hartcodierten englischen Beschreibungstexte — bleiben verbatim (kein i18n;
das Original i18n-isiert diese Strings ebenfalls nicht).

```ts
export interface RaidLevelInfo {
  level: string;
  name: string;
  description: string;
  minDisks: number;
  redundancy: string;
  capacity: string;
  performance: string;
  recommended?: boolean;
}
export const RAID_LEVELS: RaidLevelInfo[];
```

### `raid-setup/raidWizardHelpers.ts` (pure Helfer)

DOM-freie, testbare Logik:

```ts
// aus calculateArrayCapacity — pure; behält den Dev-Quirk (5 GB pro Disk) verbatim
export function calculateArrayCapacity(level: string, diskCount: number): string;
// aus MDADM_NAME_REGEX + Längen-Check
export function isValidArrayName(name: string): boolean;
```

- `calculateArrayCapacity` reproduziert die Switch-Logik (raid0=n×, raid1=1×,
  raid5=(n-1)×, raid6=(n-2)×, raid10=(n/2)×), `diskSize = 5 * 1024**3`, `formatBytes`
  für die Ausgabe; `diskCount === 0` → `'0 GB'`. **Verbatim** — der 5-GB-Dev-Quirk
  wird nicht gefixt.
- `isValidArrayName`: `/^md([0-9]+|_[a-zA-Z0-9]+)$/.test(name) && name.length <= 32`.

### `hooks/useRaidSetupWizard.ts` (Logik)

Kapselt State + Navigation + Handler:

- **State:** `currentStep` (`'select-disks' | 'raid-level' | 'confirm'`),
  `selectedDisks`, `selectedRaidLevel`, `arrayName`, `busy`.
- **Derivations:** `freeDisks` (nicht in_raid/os_disk), `isArrayNameValid`
  (via `isValidArrayName`), `getSelectedRaidInfo`, `canProceedFromDiskSelection`,
  `canProceedFromRaidLevel`.
- **Handler:** `toggleDiskSelection`, `setCurrentStep`, `setSelectedRaidLevel`,
  `setArrayName`, `handleSubmit` (baut `devices` aus erster Partition/Disk, ruft
  `createArray`, Toast + `onSuccess`/`onClose`).

**Signatur (Skizze):**

```ts
function useRaidSetupWizard(
  availableDisks: AvailableDisk[],
  onClose: () => void,
  onSuccess: () => void,
): {
  currentStep: WizardStep;
  setCurrentStep: (s: WizardStep) => void;
  selectedDisks: string[];
  toggleDiskSelection: (name: string) => void;
  selectedRaidLevel: string;
  setSelectedRaidLevel: (l: string) => void;
  arrayName: string;
  setArrayName: (n: string) => void;
  busy: boolean;
  freeDisks: AvailableDisk[];
  isArrayNameValid: boolean;
  getSelectedRaidInfo: () => RaidLevelInfo | undefined;
  canProceedFromDiskSelection: () => boolean;
  canProceedFromRaidLevel: () => boolean;
  handleSubmit: (e: FormEvent) => Promise<void>;
}
```

Der Hook nutzt `useTranslation('system')` intern (Toast-Meldungen in `handleSubmit`).

### Step-Subkomponenten (`raid-setup/*`)

Rein präsentational — Props rein, Callbacks raus, kein eigener State, kein API-Call.
i18n via `useTranslation('system')` wo im Original genutzt.

- **`RaidWizardStepIndicator`** — Fortschrittsleiste. Props: `currentStep`.
- **`RaidDiskSelectionStep`** — Disk-Liste + Auswahl. Props: `freeDisks`,
  `selectedDisks`, `onToggleDisk`, `canProceed`, `onCancel`, `onNext`.
- **`RaidLevelSelectionStep`** — RAID-Level-Auswahl (gefiltert nach `minDisks`).
  Props: `selectedDisks`, `selectedRaidLevel`, `onSelectLevel`, `canProceed`,
  `onBack`, `onCancel`, `onNext`.
- **`RaidConfirmationStep`** — Name-Input + Zusammenfassung + Warnung + Submit-Form.
  Props: `arrayName`, `onArrayNameChange`, `isArrayNameValid`, `raidInfo`,
  `capacity`, `selectedDisks`, `busy`, `onBack`, `onCancel`, `onSubmit`.

### `RaidSetupWizard.tsx` (Orchestrator)

- Ruft `useRaidSetupWizard`, destrukturiert State + Handler.
- Berechnet `capacity` via `calculateArrayCapacity(selectedRaidLevel, selectedDisks.length)`
  für den Confirm-Step.
- Rendert Modal-Shell (Backdrop + `onClose`/`stopPropagation`) mit
  `RaidWizardStepIndicator` und dem bedingt gerenderten aktiven Step.
- Enthält keine Zustandslogik mehr.

## Test-Strategie (T7-konform)

Aktuell 0 Tests → Netto-Zugewinn.

- **`raidWizardHelpers.test.ts`** — der Kern:
  - `calculateArrayCapacity`: je RAID-Level (0/1/5/6/10) das korrekte Ergebnis bei
    definierter Disk-Zahl; `diskCount === 0` → `'0 GB'`; unbekanntes Level → Default.
  - `isValidArrayName`: gültig (`md0`, `md_backup`), ungültig (`raid0`, `md`,
    Leerstring, > 32 Zeichen, Sonderzeichen).
- **`useRaidSetupWizard.test.tsx`** — `toggleDiskSelection` (an/aus),
  `canProceedFromDiskSelection` (≥ 2), `canProceedFromRaidLevel` (≥ minDisks),
  `handleSubmit` ruft `createArray` mit korrektem Payload (erste Partition bevorzugt)
  und triggert `onSuccess`/`onClose` (mit gemocktem `createArray`).
- **Step-Subkomponenten** — je ein leichter Render-/Interaktions-Test (z.B.
  DiskSelection zeigt „no disks"-Zustand, Next disabled unter Schwelle, Toggle feuert
  Callback; StepIndicator hebt den aktiven Schritt hervor).

## Verifikation vor PR

- `npx vitest run` (Frontend-Suite grün, neue Tests inklusive).
- `npx eslint .` (0-Error-Gate).
- `npm run build` (tsc -b).
- Whole-Branch-Review (Multi-Agent).
- `components/CLAUDE.md`-Eintrag: neue `raid-setup/`-Zeile ergänzen.
