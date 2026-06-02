# PowerMenu: Schnell-Option „Desktop deaktivieren" — Design

**Date:** 2026-06-02
**Status:** Approved
**Author:** Sven (Xveyn) + Claude

## Problem

Das KDE-Desktop-Deaktivieren (Bildschirme via DPMS ausschalten, damit die dGPU
deep-idlen kann) ist heute nur über **System Control → Sleep → Desktop (KDE)**
(`DesktopTogglePanel`) erreichbar. Für den häufigen „mach den Bildschirm aus"-Griff
fehlt eine Schnell-Option im global sichtbaren PowerMenu (Power-Button oben rechts).

## Was bereits existiert (wiederverwendet)

- **Backend:** `POST /api/system/sleep/desktop/disable` → `kscreen-doctor --dpms off`
  (`LinuxDesktopBackend.disable`). Schaltet nur die Display-Ausgänge aus; KWin/sddm-Session
  läuft weiter, dGPU fällt von ~78W auf ~18W. **Reversibel & ungefährlich.**
- **Status:** `GET /api/system/sleep/desktop/status` → `DesktopStatus { state, display_manager, detail }`,
  `state ∈ {running, stopped, unknown}`. `running` = mind. 1 aktives DRM-Display.
- **API-Client:** `client/src/api/desktop.ts` — `getDesktopStatus()`, `disableDesktop()`, `enableDesktop()`.
- **PowerMenu:** `client/src/components/PowerMenu.tsx` — Admin-Aktionen (Restart/Shutdown/Sleep/Standby)
  + Logout. Sleep/Standby erscheinen nur wenn `getSleepStatus()` beim Öffnen erfolgreich ist
  (`sleepAvailable`-Muster). Bestätigungspflichtige Aktionen laufen über `confirmAction`-State +
  `ConfirmDialog`; Logout schließt sofort ohne Dialog.

> Hinweis: Der Kommentar in `api/desktop.ts` („stoppt den Display-Manager / Session neu starten")
> ist **veraltet**. Maßgeblich sind `DesktopTogglePanel`-Doku und `desktop_backend.py`:
> es ist ein DPMS-Screen-Off, kein Service-Stop.

## Lösung

Eine **Ein-Weg-Schnellaktion** „Desktop deaktivieren" im PowerMenu-Admin-Block, die nur erscheint,
wenn die Bildschirme gerade laufen (`state === 'running'`). Klick → sofort `disableDesktop()`
(kein Bestätigungsdialog) + Toast. Re-Aktivieren bleibt der Sleep-Seite vorbehalten.

### Warum Ein-Weg + nur bei `running`

Headless-Server melden `state === 'stopped'` (0 Displays), nicht `unknown` — eine reine
Sichtbarkeitslogik über „nicht unknown" würde den Punkt fälschlich auf Servern ohne Desktop zeigen.
`state === 'running'` ist das eindeutige Signal „es gibt aktive Bildschirme, die man ausschalten kann".
Das vermeidet Menü-Clutter ohne Backend-Änderung und deckt den Wunsch („schnell deaktivieren") exakt ab.

## Architektur

**Einzige geänderte Komponente:** `client/src/components/PowerMenu.tsx`. Kein Backend-, Schema-,
Migrations- oder API-Client-Change.

### Zustand & Laden

Neuer State `const [desktopState, setDesktopState] = useState<DesktopState | null>(null);`.

Im bestehenden `useEffect` (`isOpen && isAdmin`) zusätzlich:

```tsx
getDesktopStatus()
  .then((s) => setDesktopState(s.state))
  .catch(() => setDesktopState(null));
```

(parallel zum vorhandenen `getSleepStatus()`-Aufruf; unabhängig von `sleepAvailable`).

### Menüpunkt

Im Admin-Block, **nach** dem Standby-Button und **vor** dem `border-t`-Divider, nur gerendert wenn
`desktopState === 'running'`:

```tsx
{desktopState === 'running' && (
  <button
    onClick={handleDisableDesktop}
    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-cyan-500/10"
  >
    <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/10">
      <MonitorOff className="h-4 w-4 text-cyan-400" />
    </div>
    <div>
      <p className="text-sm font-medium text-slate-100">
        {t('powerMenu.desktopDisable', 'Disable desktop')}
      </p>
      <p className="text-xs text-slate-400">
        {t('powerMenu.desktopDisableDesc', 'Turn off displays (saves GPU power)')}
      </p>
    </div>
  </button>
)}
```

`MonitorOff` wird aus `lucide-react` importiert (zur bestehenden Icon-Import-Zeile hinzufügen).

### Klick-Handler (sofort, kein Dialog)

```tsx
const handleDisableDesktop = async () => {
  setIsOpen(false);
  try {
    const result = await disableDesktop();
    if (result.success) {
      toast.success(t('powerMenu.desktopDisabled', 'Desktop disabled'));
    } else {
      toast.error(result.message || t('powerMenu.desktopDisableFailed', 'Failed to disable desktop'));
    }
  } catch {
    toast.error(t('powerMenu.desktopDisableFailed', 'Failed to disable desktop'));
  }
};
```

Das Menü schließt sofort (wie Logout) → kein Doppelklick-Schutz nötig. `disableDesktop` wird
aus `../api/desktop` importiert.

### i18n

Neue Keys im `common`-Namespace unter `powerMenu` (DE + EN), Inline-Defaults wie bei den
bestehenden `powerMenu`-Strings:

| Key | DE | EN |
|---|---|---|
| `powerMenu.desktopDisable` | „Desktop deaktivieren" | „Disable desktop" |
| `powerMenu.desktopDisableDesc` | „Bildschirme ausschalten (GPU spart Strom)" | „Turn off displays (saves GPU power)" |
| `powerMenu.desktopDisabled` | „Desktop deaktiviert" | „Desktop disabled" |
| `powerMenu.desktopDisableFailed` | „Desktop konnte nicht deaktiviert werden" | „Failed to disable desktop" |

## Edge Cases

| Fall | Verhalten |
|---|---|
| `getDesktopStatus()` schlägt fehl | `desktopState = null` → Punkt ausgeblendet |
| `state === 'stopped'` (inkl. headless) | Punkt ausgeblendet |
| `state === 'unknown'` | Punkt ausgeblendet |
| `disableDesktop()` schlägt fehl | Fehler-Toast; Menü ist bereits geschlossen |
| Nutzer ist kein Admin | Gesamter Admin-Block (inkl. Punkt) nicht gerendert |
| Status zwischen Öffnen und Klick veraltet (Displays inzwischen aus) | `disableDesktop()` ist idempotent (`--dpms off` erneut) → Erfolg/harmlos |

## Security

Keine neue Datenexposition oder neue Endpunkte. Der Punkt liegt im `isAdmin`-Block; die
Backend-Endpunkte unter `/api/system/sleep/desktop/*` haben ihre bestehende Admin-Absicherung.
Keine sensiblen Daten im Status (`state`, `display_manager`, `detail`).

## Tests

`client/src/__tests__/components/PowerMenu.test.tsx` (neu — PowerMenu hat bisher keinen Test).
Mocks: `../../api/desktop` (`getDesktopStatus`, `disableDesktop`), `../../api/sleep` (`getSleepStatus`),
`react-hot-toast`.

| Test | Verifiziert |
|---|---|
| `zeigt Desktop-Deaktivieren wenn running` | `isAdmin`, `getDesktopStatus`→`{state:'running'}`, Menü offen → Button „Disable desktop" sichtbar |
| `verbirgt Desktop-Deaktivieren wenn stopped` | `getDesktopStatus`→`{state:'stopped'}` → Button nicht im DOM |
| `verbirgt Desktop-Deaktivieren bei Status-Fehler` | `getDesktopStatus` rejected → Button nicht im DOM |
| `Klick ruft disableDesktop + Erfolg-Toast` | Klick auf den Button → `disableDesktop` aufgerufen, `toast.success` |
| `verbirgt Punkt für Nicht-Admin` | `isAdmin={false}` → Button nicht sichtbar (Admin-Block nicht gerendert) |

Hinweis: `getSleepStatus` in den Tests mit `mockResolvedValue` stubben, damit das `sleepAvailable`-`useEffect`
nicht stört; der Desktop-Punkt ist unabhängig davon.

## Build Order

1. `MonitorOff`-Import + `disableDesktop`/`getDesktopStatus`-Import + `DesktopState`-Typ in `PowerMenu.tsx`
2. `desktopState`-State + Status-Fetch im bestehenden `useEffect`
3. `handleDisableDesktop`-Handler
4. Menüpunkt (conditional auf `desktopState === 'running'`)
5. i18n-Keys (DE + EN `common.json`)
6. Vitest-Test
7. `cd client && npm run build` + `npm test -- PowerMenu` grün

## Out of Scope

- Umschalter/Re-Aktivieren im PowerMenu (bleibt auf der Sleep-Seite)
- Bestätigungsdialog (Aktion ist reversibel/ungefährlich → sofort)
- Backend-`available`-Flag / Panel-Gating-Korrektur (separat, falls je gewünscht)
- Mobile/Pi-Darstellung (PowerMenu unverändert)

## References

- `client/src/components/PowerMenu.tsx` — zu ändernde Komponente
- `client/src/api/desktop.ts` — `getDesktopStatus()`, `disableDesktop()` (bestehend)
- `client/src/components/power/DesktopTogglePanel.tsx` — bestehende Voll-UI (Sleep-Seite)
- `backend/app/services/power/desktop_backend.py` — `--dpms off`-Semantik (maßgeblich)
- `docs/superpowers/plans/2026-05-30-desktop-toggle.md` — Ursprungs-Feature
