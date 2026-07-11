# SleepConfigPanel-Zerlegung (F2) — Design

> Stand: 2026-07-11. Basis `main` (nach #399). Adressiert Assessment-Finding **F2**
> (`components/power/SleepConfigPanel.tsx` = 721 Zeilen, **30+ `useState`** — der
> State-schwerste Kandidat). Folgt dem #301/#399-Muster (Feature-Verzeichnis mit
> extrahierten Subkomponenten) sowie dem `useGpuPower`-Draft-Muster für die
> Formular-State-Konsolidierung.

## Ziel

`SleepConfigPanel.tsx` von 721 Zeilen auf **~150 Zeilen** reduzieren und den
30-useState-Smell **echt beseitigen** (nicht nur verlagern), indem:
- die ~20 Sleep-Config-Formfelder in **ein** Config-Objekt (Hook `useSleepConfigForm`),
- die 6 Fritz!Box-Felder in **ein** Objekt (Hook `useFritzBoxForm`),
- die 8 Sektions-Cards und die lokalen Primitives in `components/power/sleep-config/`
extrahiert werden. Verhaltenserhaltend.

**Nicht** Ziel: i18n-Umbau der hardcodierten Strings, TanStack-Migration, Änderung
an Load-/Save-/Test-Verhalten, neue Felder/Endpoints.

## Ausgangslage

`SleepConfigPanel.tsx` (721 Z.) enthält:
- **~35 `useState`** in 3 Gruppen: Panel (6: `capabilities`, `loading`, `busy`,
  `helpOpen`, `coreUptimeMasterOn`, `alwaysAwakeOn`; + `presenceStatus`),
  Sleep-Config-Form (20), Fritz!Box (8).
- `loadData()` — lädt Config + Capabilities + Fritz!Box-Config + Sleep-Status
  (letztere zwei best-effort im try/catch), seedet die Form-State.
- `syncFormState(c)` — Response → 20 Setter.
- `handleSave()` — 20 Formfelder → `updateSleepConfig`-Payload + `updateFritzBoxConfig`,
  unified Toast.
- `handleFbTest()` — `testFritzBoxConnection` + Toast.
- 8 Sektions-Cards im JSX + Save-Button.
- 6 lokale Helper unten (~185 Z.): `Toggle`, `ToggleRow`, `NumberInput`, `CapBadge`,
  `CapabilityHelp` + `getHelpEntries`/`HelpEntry`.

Importer (bleiben unberührt): `components/power/index.ts` (Barrel-Re-Export) und
`pages/SleepMode.tsx`. **Die Panel-Datei bleibt an ihrem Pfad** — nur die Interna
werden zum Orchestrator umgeschrieben.

## Architektur / Dateilayout

```
hooks/useSleepConfigForm.ts     # 20 Config-Felder → 1 Objekt + update/syncFromResponse/toPayload
hooks/useFritzBoxForm.ts        # 6 FB-Felder + config + testing + test() + syncFromConfig/toPayload
components/power/sleep-config/
  index.ts                      # Barrel
  SleepFormControls.tsx         # Toggle, ToggleRow, NumberInput (Primitives)
  CapabilitiesCard.tsx          # CapBadge + CapabilityHelp + getHelpEntries + HelpEntry + Card
  IdleDetectionCard.tsx
  EscalationCard.tsx
  PresenceCard.tsx
  ScheduleCard.tsx
  WolCard.tsx
  FritzBoxCard.tsx
  SleepBehaviorCard.tsx
components/power/SleepConfigPanel.tsx   # Rewrite: Orchestrator (Pfad unverändert)
__tests__/hooks/useSleepConfigForm.test.ts
__tests__/hooks/useFritzBoxForm.test.ts
__tests__/components/power/sleep-config/*.test.tsx
__tests__/components/power/SleepConfigPanel.test.tsx
```

## State-Konsolidierung

### `useSleepConfigForm`

Ersetzt die 20 einzelnen `useState` durch **ein** `SleepConfigForm`-Objekt:

```ts
interface SleepConfigForm {
  autoIdleEnabled: boolean; idleTimeout: number; idleCpuThreshold: number;
  idleDiskIoThreshold: number; idleHttpThreshold: number;
  escalationEnabled: boolean; escalationMinutes: number;
  scheduleEnabled: boolean; scheduleSleepTime: string; scheduleWakeTime: string;
  scheduleMode: ScheduleMode;
  wolMac: string; wolBroadcast: string;
  pauseMonitoring: boolean; pauseDiskIo: boolean; reducedTelemetry: number;
  diskSpindown: boolean;
  presenceEnabled: boolean; presenceMode: PresenceMode; presenceTimeout: number;
}

useSleepConfigForm(): {
  form: SleepConfigForm;
  update: (patch: Partial<SleepConfigForm>) => void;
  syncFromResponse: (c: SleepConfigResponse) => void;
  toPayload: () => SleepConfigUpdate;
}
```

- Default-`form` = die aktuellen `useState`-Defaults (autoIdle false, idleTimeout 15,
  idleCpuThreshold 5.0, idleDiskIoThreshold 0.5, idleHttpThreshold 5.0,
  escalation false/60, schedule false/'23:00'/'06:00'/'soft', wol ''/'',
  pauseMonitoring true, pauseDiskIo true, reducedTelemetry 30, diskSpindown true,
  presence true/'active'/3).
- `update(patch)` — `setForm(f => ({ ...f, ...patch }))`. Das rufen die Cards auf.
- `syncFromResponse(c)` — mappt `SleepConfigResponse` → Form (der bisherige
  `syncFormState`, jetzt als ein `setForm({...})`).
- `toPayload()` — mappt Form → `SleepConfigUpdate`, **byte-genau** wie das aktuelle
  `handleSave`-Objekt (u. a. `wol_mac_address: wolMac || null`,
  `wol_broadcast_address: wolBroadcast || null`).

### `useFritzBoxForm`

```ts
interface FritzBoxForm { host: string; port: number; username: string; password: string; mac: string; enabled: boolean; }

useFritzBoxForm(): {
  form: FritzBoxForm;
  update: (patch: Partial<FritzBoxForm>) => void;
  config: FritzBoxConfig | null;          // geladene Config (für has_password-Anzeige)
  syncFromConfig: (fb: FritzBoxConfig) => void;   // setzt config + form aus fb
  // toPayload liefert genau das Objekt, das das aktuelle handleSave an updateFritzBoxConfig übergibt:
  // { host, port, username, ...(password ? { password } : {}), nas_mac_address: mac || undefined, enabled }
  toPayload: () => Parameters<typeof updateFritzBoxConfig>[0];
  testing: boolean;
  test: () => Promise<void>;              // testFritzBoxConnection + Erfolg/Fehler-Toast
}
```

- Default-`form` = aktuelle Defaults (`host` '192.168.178.1', `port` 49000, rest ''/false).
- `syncFromConfig(fb)` — setzt `config` + `form` (host/port/username/mac/enabled; **password bleibt ''**, wie aktuell).
- `test()` — der bisherige `handleFbTest` (setTesting, testFritzBoxConnection, success/error-Toast).

Beide Hooks: **kein TanStack** (nutzer-getriggerte Config-Daten, konsistent mit der
SharesPage/`useCloudExports`-Entscheidung). Folgt dem `useGpuPower`-Draft-Muster.

## Sektions-Cards

Jede Card ist reine Präsentation (Form-Slice + `update` + ggf. Kontext rein, kein
Fetch, kein eigener State außer trivialem). JSX verbatim aus dem Panel übernommen,
**hardcodierte Strings unverändert** (kein i18n-Umbau).

| Card | Inhalt | Props (zusätzlich zu Form/update) |
|---|---|---|
| `CapabilitiesCard` | Badges + Setup-Help (enthält `CapBadge`, `CapabilityHelp`, `getHelpEntries`, `HelpEntry`) | `capabilities`, `helpOpen`, `onToggleHelp` |
| `IdleDetectionCard` | Toggle + 4 NumberInputs | — |
| `EscalationCard` | Toggle + 1 NumberInput | — |
| `PresenceCard` | Toggle + Mode-Select + Timeout + Suppress-Banner | `presenceStatus` |
| `ScheduleCard` | Toggle + 2 Time-Inputs + Mode-Select + Override-Banner | `coreUptimeMasterOn`, `alwaysAwakeOn` |
| `WolCard` | 2 Text-Inputs + Detected-MAC-Button | `capabilities` (für `own_mac_address`) |
| `FritzBoxCard` | FB-Form + Test-Button | `config`, `testing`, `onTest`, `capabilities` |
| `SleepBehaviorCard` | 3 ToggleRows + 1 NumberInput | — |

`SleepFormControls.tsx` exportiert die 3 Primitives `Toggle`, `ToggleRow`,
`NumberInput` (verbatim). `CapBadge` + `CapabilityHelp` + `getHelpEntries` wandern in
`CapabilitiesCard.tsx` (dort einzig genutzt).

## Panel-Orchestrierung

`SleepConfigPanel.tsx` behält nur die panel-eigene State (**~7 statt 35**):
`capabilities`, `loading`, `busy`, `helpOpen`, `coreUptimeMasterOn`,
`alwaysAwakeOn`, `presenceStatus`. Verdrahtet die zwei Form-Hooks.

- `loadData()` — unverändertes Verhalten inkl. best-effort try/catch: lädt
  Config+Caps (Pflicht), Fritz!Box-Config + Sleep-Status (best-effort), ruft
  `sleepForm.syncFromResponse(configData)` und `fbForm.syncFromConfig(fb)`, setzt
  `capabilities`/`coreUptimeMasterOn`/`alwaysAwakeOn`/`presenceStatus`.
- `handleSave()` — `updateSleepConfig(sleepForm.toPayload())` +
  (im try) `updateFritzBoxConfig(fbForm.toPayload())`, gleiche Toast-Sequenz +
  `busy`-Guard wie jetzt.
- Loading-Skeleton unverändert.
- Render: `<CapabilitiesCard>` … 8 Cards … Save-Button.

## Tests (breit + Panel-Integration)

Alle unter `__tests__/…`, T7-Konvention (**keine Tailwind-Klassen-Assertions**;
role/text/label). `react-i18next` gemockt zu `t:(k)=>k`; API-Module + `react-hot-toast`
gemockt.

- **`useSleepConfigForm.test.ts`** (Kern-Risiko): Round-Trip — `SleepConfigResponse`-Fixture
  → `syncFromResponse` → `toPayload` ergibt das erwartete `SleepConfigUpdate` (inkl.
  der `|| null`-Fälle für WoL); plus `update()` patcht ein Feld ohne die anderen zu
  verlieren; Default-Form stimmt.
- **`useFritzBoxForm.test.ts`**: `syncFromConfig` (password bleibt ''), `toPayload`
  (password nur wenn gesetzt, `nas_mac_address: mac || undefined`), `test()` Erfolg
  + Fehler → richtiger Toast, `testing`-Flag.
- **Card-Tests** (`sleep-config/*.test.tsx`): je Card conditional-Rendering +
  `update`-Wiring — Idle-Inputs nur bei enabled; Escalation-Input nur bei enabled;
  Presence-Suppress-Banner bei `presenceStatus.suppressing_suspend`; Schedule-Override-
  Banner bei `coreUptimeMasterOn`/`alwaysAwakeOn`; WoL-Detected-Button nur wenn
  `own_mac_address` ≠ aktuell; FritzBox has_password-Anzeige + Test-Button →
  `onTest`; CapabilitiesCard: `getHelpEntries` (fehlende Tools → Einträge, alle
  vorhanden → keine).
- **`SleepFormControls.test.tsx`**: Toggle (on/off → onChange), ToggleRow (Label +
  Toggle), NumberInput (Eingabe → onChange(Number)).
- **`SleepConfigPanel.test.tsx`** (Integration): Hooks/APIs gemockt, load seedet die
  Cards, ein Feld ändern → Save-Klick ruft `updateSleepConfig` mit erwartetem Payload
  (und `updateFritzBoxConfig`).

## Nicht-Ziele

- Kein i18n-Umbau — hardcodierte englische/deutsche Strings verbatim übernehmen.
- Kein TanStack für Sleep-Config/Fritz!Box.
- Keine Änderung an Load-/Save-/Test-Logik, Endpoints, Feldern.
- Primitives bleiben `sleep-config`-lokal (kein Promoten nach `ui/`).
- Panel-Datei bleibt am Pfad `components/power/SleepConfigPanel.tsx` (Importer unberührt).

## Verifikation

- `SleepConfigPanel.tsx` < 500 (Ziel ~150); keine `sleep-config/*`-Datei > ~200 Z.
- `npx vitest run` grün (neue Tests + Bestand).
- `eslint .` 0 Fehler, `npm run build` (tsc -b) grün.
- Manuelle Sichtprüfung: alle 8 Sektionen rendern; Toggles/Inputs schreiben; Save
  persistiert (Payload unverändert); Fritz!Box-Test; Setup-Help-Akkordeon.
- `components/CLAUDE.md` (power-Zeile) um den `sleep-config/`-Hinweis + `hooks/CLAUDE.md`
  um die zwei Form-Hooks ergänzen.
