# FanCurveChart.tsx Zerlegung — Design (F2 / #301)

**Datum:** 2026-07-12
**Issue:** #301 (F2 — Komponenten über 500 Zeilen)
**Komponente:** `client/src/components/fan-control/FanCurveChart.tsx` (577 Zeilen)

## Ziel

`FanCurveChart.tsx` verletzt die 500-Zeilen-Konvention. Anders als die bisher
zerlegten Komponenten ist dies eine **eng gekoppelte interaktive Chart-Komponente**
(Drag/Click/Touch mit Document-Level-Listenern, Koordinaten-Mathematik über das
Recharts-DOM, Timing-Tricks). Zerlegung **verhaltenserhaltend**:

- **Vorher:** 577 Zeilen — Interaktionslogik + Koordinaten-Mathe + Recharts-Rendering + Präsentation in einer Datei.
- **Nachher:** Orchestrator ~170 Zeilen; alle Units unter der Konvention.
- **Kein** Verhaltens-, Prop-Interface- oder Rendering-Wechsel nach außen. Öffentliche
  `FanCurveChartProps`, Default-Export und der Barrel `fan-control/index.ts` bleiben
  unverändert. Konsument `FanDetails.tsx` bleibt unberührt.

## Ausgangslage

- Konsument: nur `FanDetails.tsx` (via `import FanCurveChart from './FanCurveChart'`).
- Aktuell **keine** eigenen Tests → die Zerlegung bringt netto neue Testabdeckung
  (insbesondere die pure Geometrie).
- Recharts (`ComposedChart`, `Line`, `Scatter`, Achsen, `ReferenceLine`) bleibt
  im Orchestrator.

## Kritisches Fidelity-Detail — zwei getrennte Rechenpfade

Es gibt **zwei unterschiedliche** Pixel→Wert-Umrechnungen, die NICHT vereinheitlicht
werden dürfen:

1. **Click / Tap-to-add** (`pixelToValue`): rundet Temp/PWM auf **Integer**, liefert
   `inBounds`, nutzt `getChartBounds()` mit Fallback-Kette (CartesianGrid →
   horizontal-lines → surface-minus-margins).
2. **Drag** (`updatePointPosition`): rundet auf **0.1**, liest den Grid **direkt**
   via `querySelector('.recharts-cartesian-grid')` **ohne** Fallback.

Beide Pfade bleiben als getrennte pure Funktionen erhalten. Der DOM-Read
(`getBoundingClientRect`, `querySelector`, die Fallback-Kette) bleibt im Hook;
nur die reine Arithmetik wird herausgelöst.

## Zielstruktur

```
components/fan-control/
  FanCurveChart.tsx                 # Orchestrator (~170 Zeilen)
  fanCurveGeometry.ts               # PURE: computeChartValue / computeDraggedPoint / findNearestPointIndex
  fan-curve-chart/
    FanCurveTooltip.tsx             # CustomTooltip
    FanChartLegend.tsx              # Legende
    FanChartHint.tsx                # Hilfe-/Grenzhinweis-Text
    index.ts                        # interner Barrel
hooks/
  useFanCurveInteraction.ts         # State + Refs + Effekte + DOM-Bounds + Handler
```

`fan-control/index.ts` bekommt **keine** neuen öffentlichen Re-Exports — Hook,
Geometrie und `fan-curve-chart/*` sind Implementierungsdetails von `FanCurveChart`.

## Einheiten

### `fanCurveGeometry.ts` (pure, testbar)

DOM-freie Arithmetik. Nimmt bereits aufgelöste `bounds`/`plotRect` (Rect mit
`left/top/width/height`) und Client-Koordinaten entgegen.

```ts
export interface ChartValueConfig {
  emergencyTemp: number;
  minPWM: number;
  maxPWM: number;
}

export interface RectLike { left: number; top: number; width: number; height: number; }

// aus pixelToValue: INTEGER-Rundung + inBounds-Flag
export function computeChartValue(
  clientX: number, clientY: number, bounds: RectLike, cfg: ChartValueConfig,
): { temp: number; pwm: number; inBounds: boolean };

// aus updatePointPosition: 0.1-Rundung, clamp temp∈[0,emergencyTemp+10], pwm∈[minPWM,maxPWM]
export function computeDraggedPoint(
  clientX: number, clientY: number, plotRect: RectLike, cfg: ChartValueConfig,
): { temp: number; pwm: number };

// aus findPointNear: nächster Punkt-Index (sortierte Reihenfolge) oder null
export function findNearestPointIndex(
  clientX: number, clientY: number, bounds: RectLike,
  sortedPoints: { temp: number; pwm: number }[], emergencyTemp: number, hitRadius?: number, // default 10
): number | null;
```

Regeln 1:1 wie im Original:
- `computeChartValue`: `tempRange = emergencyTemp + 10`; `temp = round((x/width)*tempRange)`;
  `pwm = round(100 - (y/height)*100)`; clamp temp∈[0,emergencyTemp+10], pwm∈[minPWM,maxPWM];
  `inBounds = x>=-5 && x<=width+5 && y>=-5 && y<=height+5` (x,y = client − bounds.left/top).
- `computeDraggedPoint`: `tempRange = emergencyTemp + 10`; `temp = round((x/width)*tempRange*10)/10`;
  `pwm = round((100 - (y/height)*100)*10)/10`; clamp temp∈[0,emergencyTemp+10], pwm∈[minPWM,maxPWM].
- `findNearestPointIndex`: `hitRadius=10`; für jeden sortierten Punkt
  `pointX=(temp/tempRange)*width`, `pointY=((100-pwm)/100)*height`, euklidische Distanz;
  nächster Punkt mit `dist<hitRadius`, sonst `null`.

### `hooks/useFanCurveInteraction.ts` (Interaktionslogik)

Verbatim-Port der gesamten Interaktions-/State-Logik. Kapselt:

- **State:** `draggingIndex`, `localPoints`.
- **Refs:** `chartRef`, `overlayRef`, `localPointsRef`, `wasDraggingRef`,
  `canEditRef`, `maxPointsRef`, `onPointsChangeRef`.
- **Effekte:** Ref-Sync (canEdit/maxPoints/onPointsChange), externe→lokale
  Points-Sync (nicht während Drag), `localPointsRef`-Sync.
- **Derivations:** `canEdit`, `pointsWithIndices`, `sortedPoints`, `chartData`.
- **DOM-Bounds:** `getChartBounds` (Fallback-Kette, unverändert im Hook).
- **Handler:** `handleRemovePoint`, `handleOverlayMouseDown`, `handleOverlayClick`,
  `handleOverlayContextMenu`, `handleOverlayTouchStart` (Document-Level-Listener,
  `requestAnimationFrame`-Click-Suppression, Touch-Tap-vs-Drag — alles verbatim).

Der Hook ruft die pure Geometrie an den Stellen von `pixelToValue`/`findPointNear`/
`updatePointPosition`. Die interne `updatePointPosition`-Logik liest weiterhin den
Grid direkt (kein Fallback) und übergibt die Rect an `computeDraggedPoint`.

**Signatur (Skizze):**

```ts
function useFanCurveInteraction(
  points: FanCurvePoint[],
  onPointsChange: (points: FanCurvePoint[]) => void,
  cfg: { minPWM: number; maxPWM: number; emergencyTemp: number; isReadOnly: boolean; minPoints: number; maxPoints: number },
): {
  chartRef: React.RefObject<HTMLDivElement>;
  overlayRef: React.RefObject<HTMLDivElement>;
  draggingIndex: number | null;
  canEdit: boolean;
  localPoints: FanCurvePoint[];
  sortedPoints: Array<FanCurvePoint & { originalIndex: number }>;
  chartData: ChartDataPoint[];
  handleOverlayMouseDown: (e: React.MouseEvent) => void;
  handleOverlayClick: (e: React.MouseEvent) => void;
  handleOverlayContextMenu: (e: React.MouseEvent) => void;
  handleOverlayTouchStart: (e: React.TouchEvent) => void;
}
```

`ChartDataPoint` (`extends FanCurvePoint { isCurrentPoint?; originalIndex? }`) wird
in den Hook mitverschoben und exportiert (Orchestrator + Tooltip brauchen den Typ).

### Präsentations-Subkomponenten (`fan-curve-chart/*`)

Rein präsentational, verbatim aus dem Original. i18n via
`useTranslation(['system','common'])` wo nötig.

- **`FanCurveTooltip`** — der `CustomTooltip` (nutzt `formatNumber`, i18n-Keys für
  current/curvePoint). Props: Recharts-Tooltip-Shape (`active?`, `payload?`).
- **`FanChartLegend`** — Legenden-Block (Curve Points / Current Operating Point /
  Emergency Temp). Props: `currentTemp: number | null`, `emergencyTemp: number`.
- **`FanChartHint`** — Editier-Hinweistext inkl. min/max-Zusätze. Props:
  `pointCount: number`, `minPoints: number`, `maxPoints: number`. (Nur gerendert,
  wenn `canEdit` — Bedingung bleibt im Orchestrator.)

### `FanCurveChart.tsx` (Orchestrator)

- Ruft `useFanCurveInteraction`, destrukturiert Refs/State/Handler.
- Behält `renderDot` als lokalen `useCallback` (hängt an `draggingIndex`/`canEdit`,
  eng an die Recharts-`Line` gekoppelt).
- Rendert `ResponsiveContainer`/`ComposedChart` (Achsen, `ReferenceLine`s, `Line`
  mit `renderDot`, current-point `Scatter`), das transparente Overlay-`div`
  (verdrahtet mit den Hook-Handlern), `FanChartLegend`, bedingt `FanChartHint`.
- Enthält keine Interaktions-/Koordinatenlogik mehr.

## Test-Strategie (T7-konform)

Aktuell 0 Tests → Netto-Zugewinn.

- **`fanCurveGeometry.test.ts`** — der eigentliche Gewinn, deterministisch mit festen
  `RectLike`-Bounds:
  - `computeChartValue`: Integer-Rundung, PWM/Temp-Clamping, `inBounds`-Grenzen
    (innen / knapp außerhalb / weit außerhalb).
  - `computeDraggedPoint`: 0.1-Rundung, Clamping — und explizit die **Unterscheidung**
    zur Integer-Variante (gleicher Input → andere Präzision).
  - `findNearestPointIndex`: Treffer innerhalb `hitRadius`, kein Treffer außerhalb,
    nächster von mehreren, leere Punktliste → `null`.
- **`useFanCurveInteraction.test.tsx`** — Add/Remove-Pfade, soweit ohne echtes
  Layout testbar: `handleRemovePoint` respektiert `minPoints`-Guard und mappt den
  Original-Index korrekt; externe Points-Sync pausiert während Drag
  (`draggingIndex !== null`). `getChartBounds`-abhängige Handler werden mit
  gemocktem `getBoundingClientRect` angetestet, wo sinnvoll.
- **Subkomponenten** — je ein leichter Render-Test (Legende zeigt/versteckt
  Current-Operating-Point je nach `currentTemp`; Hint zeigt min/max-Zusatz; Tooltip
  rendert Temp→PWM).

## Verifikation vor PR

- `npx vitest run` (Frontend-Suite grün, neue Tests inklusive).
- `npx eslint .` (0-Error-Gate).
- `npm run build` (tsc -b).
- **Manuelles Durchspielen der Chart-Interaktion** im laufenden Frontend (FanControl-
  Seite): Punkt per Drag verschieben, Click-to-add, Right-click-remove, Touch —
  da Unit-Tests das volle Drag/Touch-Verhalten nicht abdecken.
- Whole-Branch-Review (Multi-Agent).
- `components/CLAUDE.md`-Eintrag für `fan-control/` um die `fan-curve-chart/*`-Zerlegung
  ergänzen.
