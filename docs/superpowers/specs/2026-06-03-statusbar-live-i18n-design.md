# Status Strip Live-Pills — i18n Design

**Date:** 2026-06-03
**Status:** Approved
**Area:** `client/src/components/topbar/`, `backend/app/services/status_bar/`, `client/src/i18n/locales/{de,en}/statusBar.json`

## Problem

The topbar status strip has two render paths, only one of which is internationalized:

- **Config tab** (`PillRow.tsx`) — fully i18n via `name_key` → `t('pills.*.name')`. ✅
- **Live strip** (`pillRenderers.tsx` → `Pill`) — renders `pill.label` / `pill.value` **verbatim from the backend**. ❌
- **Exception:** `AlwaysAwakePill.tsx` re-derives its label/value from i18n keys — the only correct pill.

The backend collectors (`backend/app/services/status_bar/collectors.py`) emit **hardcoded display strings** in an inconsistent mix of German and English. Examples currently shown un-/mis-translated in the live strip:

| Pill | Backend sends | Problem |
|---|---|---|
| vpn | label `"VPN"`, value `"{n} verbunden"` | label EN, value DE — mixed |
| pihole | value `"on"` / `"off"` | hardcoded EN |
| backup | value `"läuft"` / `"fehlgeschlagen"` | hardcoded DE |
| desktop | value `"An"` / `"Aus · GPU idle"` | hardcoded DE |
| sync | value `"{n} conflicts"` | hardcoded EN |
| power | label `"Dynamisch · {gov}"` | hardcoded DE |
| raid | value = raw status (`"degraded"`) | not translated |
| sleep / uploads / temp / scheduler | labels `"Sleep"` / `"Uploads"` / `"Temp"` / `"Scheduler"` | not translated |

Root cause: **the live strip has no i18n layer.** This is a structural gap, not a few missing keys.

## Chosen Approach — A1: generic key+params renderer

Translation moves to the frontend (consistent with the existing `AlwaysAwakePill` pattern). The backend sends **i18n keys + interpolation params** instead of finished strings; a single generic `PillRenderer` translates all pills. `AlwaysAwakePill` remains the only special case (client-side ticking countdown).

Rejected alternative — A2 (structured data + one renderer component per pill): 12 components of boilerplate; A2's per-pill flexibility is only needed for Always-Awake, which is already solved.

### Decisions

- **Scope:** all 12 pills converted (full consistency, not just the broken ones).
- **Live labels:** dedicated short keys (`pills.<id>.live`), separate from the longer config `name` keys, because the topbar is space-constrained.
- **`value` as `defaultValue` fallback:** for enum-ish values the collector sends both `value_key` and raw `value`; the frontend translates with `t(value_key, { defaultValue: value })`, so a missing key degrades to the raw string instead of a broken pill.

## Backend changes

### Schema — `backend/app/schemas/status_bar.py`

`PillState.label` (literal) is replaced by i18n fields:

```python
class PillState(BaseModel):
    id: PILL_IDS
    kind: PillKind
    tone: PillTone
    label_key: str                        # short live label key, e.g. "pills.vpn.live"
    label_params: Optional[dict] = None   # label interpolation (only `power` needs it)
    value: Optional[str] = None           # pure-data value ("72°C", "14:30", "3") AND defaultValue fallback
    value_key: Optional[str] = None       # translatable value key, e.g. "pills.vpn.connected"
    value_params: Optional[dict] = None   # interpolation params for value_key, e.g. {"count": 1}
    icon: Optional[str] = None
    href: str
    extra: Optional[dict] = None
```

`service.py` is unchanged in shape — `PillState(id=…, href=…, **partial)` still works; only the keys inside each collector's returned dict change.

### Collector mapping — `backend/app/services/status_bar/collectors.py`

| Pill | `label_key` (+ params) | value |
|---|---|---|
| power | `pills.power.profile` `{preset, level}` **or** `pills.power.dynamic` `{governor}` | — |
| pihole | `pills.pihole.live` | `value_key`: `pills.pihole.on` / `.off` |
| uploads | `pills.uploads.live` | `value`: `str(n)` (pure number) |
| sync | `pills.sync.live` | `value_key`: `pills.sync.conflicts` `{count}` |
| raid | `pills.raid.live` | `value_key`: `pills.raid.status.<status>` + `value` = raw status (fallback) |
| sleep | `pills.sleep.live` | `value`: `HH:MM` (pure data) |
| vpn | `pills.vpn.live` | `value_key`: `pills.vpn.connected` `{count}` |
| temp | `pills.temp.live` | `value`: `"{n}°C"` (pure data) |
| always_awake | `pills.alwaysAwake.live` | client-side (`AlwaysAwakePill`, unchanged) |
| scheduler | `pills.scheduler.live` | `value`: `str(n)` |
| backup | `pills.backup.live` | `value_key`: `pills.backup.running` / `.failed` |
| desktop | `pills.desktop.live` | `value_key`: `pills.desktop.on` / `.off` |

Notes:
- `power` is the only pill with a dynamic **label**, hence `label_params`. Preset/level names stay raw (backend enum/config data — not translated, as today).
- `raid` sends `value_key=f"pills.raid.status.{status}"` **and** `value=status`; unknown statuses fall back to the raw string via `defaultValue`.
- `always_awake` collector still sets a valid `label_key` for schema validity, but `AlwaysAwakePill` overrides label/value from its own keys; keep its `value` literal/`extra` as today.
- Collectors must never raise (the `_safe` decorator stays).

## Frontend changes

### Types — `client/src/api/statusBar.ts`

```ts
export interface PillState {
  id: PillId;
  kind: PillKind;
  tone: PillTone;
  label_key: string;
  label_params?: Record<string, unknown> | null;
  value?: string | null;
  value_key?: string | null;
  value_params?: Record<string, unknown> | null;
  icon?: string | null;
  href: string;
  extra?: Record<string, unknown> | null;
}
```

### Generic renderer — `client/src/components/topbar/pillRenderers.tsx`

```tsx
export function PillRenderer({ pill, flat }: { pill: PillState; flat?: boolean }) {
  const { t } = useTranslation('statusBar');
  if (pill.id === 'always_awake') return <AlwaysAwakePill pill={pill} flat={flat} />;

  const label = t(pill.label_key, { ...(pill.label_params ?? {}) });
  const value = pill.value_key
    ? t(pill.value_key, { ...(pill.value_params ?? {}), defaultValue: pill.value ?? '' })
    : (pill.value ?? undefined);

  const iconComp = resolveIcon(pill.icon);
  const icon = iconComp ? createElement(iconComp, { className: 'h-3.5 w-3.5' }) : undefined;
  return <Pill tone={pill.tone} label={label} value={value} href={pill.href} icon={icon} flat={flat} />;
}
```

`AlwaysAwakePill.tsx` is unchanged. The config Live Preview uses the same `PillRenderer`, so it is covered automatically.

## Locale keys — `client/src/i18n/locales/{de,en}/statusBar.json`

Existing `name` keys (config tab) stay; new `live` / value keys are added under each `pills.<id>`. German excerpt:

```jsonc
"power":   { "name": "Energieprofil",
             "profile": "{{preset}} · {{level}}", "dynamic": "Dynamisch · {{governor}}" },
"pihole":  { "name": "Pi-hole DNS", "live": "Pi-hole", "on": "An", "off": "Aus" },
"uploads": { "name": "Uploads / Downloads", "live": "Uploads" },
"sync":    { "name": "Sync", "live": "Sync", "conflicts": "{{count}} Konflikte" },
"raid":    { "name": "RAID-Zustand", "live": "RAID",
             "status": { "degraded": "Beeinträchtigt", "rebuilding": "Wird neu aufgebaut",
                         "resyncing": "Re-Sync", "inactive": "Inaktiv", "failed": "Ausgefallen" } },
"sleep":   { "name": "Sleep-Modus", "live": "Sleep" },
"vpn":     { "name": "VPN-Clients", "live": "VPN", "connected": "{{count}} verbunden" },
"temp":    { "name": "Temperatur / Lüfter", "live": "Temp" },
"alwaysAwake": { /* existing live / permanent / coreUptimeLive / coreUptimeUntil keys */ },
"scheduler": { "name": "Scheduler", "live": "Scheduler" },
"backup":  { "name": "Backup", "live": "Backup", "running": "läuft", "failed": "fehlgeschlagen" },
"desktop": { "name": "Desktop (KDE)", "live": "Desktop", "on": "An", "off": "Aus · GPU idle" }
```

English mirror: `"on": "On"`, `"off": "Off"` (desktop: `"Off · GPU idle"`), `"connected": "{{count}} connected"`, `"conflicts": "{{count}} conflicts"`, `"running": "running"`, `"failed": "failed"`, RAID statuses in English, `"dynamic": "Dynamic · {{governor}}"`.

Both languages must be updated together (project i18n rule: missing keys fall back to German).

## Testing

- **Backend collector tests:** update assertions that currently check `label == "VPN"` / `value == "1 verbunden"` to assert `label_key`, `value_key`, and `value_params` instead. Cover: vpn (count param), pihole (on/off), backup (running/failed), desktop (on/off), sync (conflicts param), power (profile vs dynamic), raid (status key + raw fallback).
- **Frontend:** add a `PillRenderer` test — `label_key`/`value_key` resolve to translated text, and the `defaultValue` fallback shows the raw `value` for an unknown `value_key`.
- **Locale parity:** verify the new keys exist in both `de` and `en` (no missing-key fallbacks).
- Run `python -m pytest` (backend) and the frontend unit tests before opening the PR.

## Accepted limitations

- Preset/level names (power) and scheduler job display names remain untranslated — they are backend config/enum data, as today.
- The status strip is web-UI only; this is an internal API shared by a single frontend+backend deploy, so no backward-compatibility shim is needed.

## Out of scope

- No changes to the config tab's `name_key` flow (already i18n).
- No new pills, no visibility/display-mode behavior changes.
- No restyling of the strip or `Pill` primitive.
