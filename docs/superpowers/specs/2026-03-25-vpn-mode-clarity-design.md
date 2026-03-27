# VPN Mode Clarity: Router-VPN vs NAS-VPN

**Date:** 2026-03-25
**Status:** Draft
**Branch:** development

## Problem

BaluHost has two VPN paths for mobile devices:

1. **Router-VPN (FritzBox):** Admin uploads a `.conf` from the FritzBox. All devices share the same config. VPN runs through the router — works even when the NAS is suspended (WoL).
2. **NAS-VPN (WireGuard Server):** BaluHost runs its own WireGuard server (`wg0`, `10.8.0.0/24`). Per-client configs with individual IPs. VPN runs through the NAS — **breaks when the NAS sleeps**.

The UI does not clearly communicate which mode is being used or warn about the WoL conflict. The `auto` fallback silently switches to NAS-VPN when no FritzBox config exists.

## Goal

- Default to Router-VPN (FritzBox)
- Keep NAS-VPN as an option
- Warn users that NAS-VPN is incompatible with Sleep/WoL
- Make the auto-fallback visible, not silent

## Changes

### 1. Mobile Token Generation UI (MobileDevicesPage.tsx)

**Current:** Three buttons — "Automatisch", "FritzBox VPN", "WireGuard Server" — with minimal context.

**New labels and behavior:**

| Current | New | Description |
|---------|-----|-------------|
| Automatisch | Automatisch | "Router-VPN bevorzugt, NAS-VPN als Fallback" |
| FritzBox VPN | Router-VPN (FritzBox) | "Nutzt die vom Admin hochgeladene Router-Konfiguration" |
| WireGuard Server | NAS-VPN (WireGuard) | "VPN laeuft direkt ueber das NAS" |

**WoL warning:** When user selects "NAS-VPN (WireGuard)", show an amber warning box:

> "VPN laeuft direkt ueber das NAS. Bei Nutzung von Sleep/WoL ist der VPN-Tunnel nicht erreichbar, solange das NAS schlaeft."

Only shown when NAS-VPN is selected (not for auto or router).

**Proactive warning when only NAS-VPN is available:** When `includeVpn` is checked and `availableVpnTypes` contains only `["wireguard"]` (no FritzBox config uploaded), show the WoL warning immediately — even though the VPN type selector is hidden (it only appears when `availableVpnTypes.length > 1`). This prevents the most common silent-fallback scenario.

**Fallback warning in QR dialog:** When `auto` mode falls back to NAS-VPN (no FritzBox config available), show an amber notice in the QR code dialog:

> "Kein Router-VPN konfiguriert. NAS-VPN wird als Fallback verwendet."

### 2. VPN Management Page (VpnManagement.tsx / System Control > Network > VPN)

**Current:** Only shows FritzBox upload section and active FritzBox config.

**New:** Add a section below the existing FritzBox section:

**"NAS-VPN (WireGuard Server)"** — collapsed/info section showing:
- Whether the NAS WireGuard server has been initialized (VPNConfig exists in DB)
- Number of active clients (if any)
- WoL warning (amber box, always visible):

  > "Hinweis: Wenn das NAS per Sleep/WoL in den Ruhezustand versetzt wird, ist der NAS-VPN-Tunnel nicht erreichbar. Fuer unterbrechungsfreien VPN-Zugang wird Router-VPN empfohlen."

This section is informational — the actual NAS-VPN client generation happens through the Mobile Devices page or API. The VPN tab label in SystemControlPage stays unchanged.

### 3. Backend: Token Generation Response

**File:** `backend/app/services/mobile.py` — `generate_registration_token()`

Add `vpn_fallback: bool` to the response when `vpn_type == "auto"` falls back to NAS-VPN (WireGuard). This lets the frontend show the fallback warning.

**Logic:** `vpn_fallback` is `True` only when all three conditions are met:
1. `vpn_type == "auto"` was requested
2. No active FritzBox config exists in DB
3. WireGuard config was successfully generated

If VPN generation fails entirely (exception at line 113), `vpn_fallback` stays `False` because no VPN config was included.

**Schema change:** Add optional field to `MobileRegistrationTokenSchema`:
```python
vpn_fallback: bool = Field(default=False, description="True when auto mode fell back to NAS-VPN")
```

### 4. Backend: available-types Endpoint

**File:** `backend/app/api/routes/vpn.py` — `get_available_vpn_types()`

No functional change. Both types remain available. The endpoint already correctly reports which types exist.

### 5. No Backend Logic Changes

- Both VPN paths remain fully functional
- `auto` priority stays: FritzBox first, WireGuard Server fallback
- `fetch-config-by-type` continues to serve both types
- No endpoints removed, no DB changes

## Files to Modify

### Frontend
- `client/src/pages/MobileDevicesPage.tsx` — VPN type labels, WoL warning, fallback notice in QR dialog, proactive warning when only WG available
- `client/src/components/VpnManagement.tsx` — Add NAS-VPN info section with WoL warning
- `client/src/api/mobile.ts` — Add `vpn_fallback?: boolean` to `MobileRegistrationToken` interface
- ~~`client/src/i18n/locales/de/common.json`~~ — Not needed; MobileDevicesPage currently hardcodes German strings (existing pattern, i18n out of scope)
- ~~`client/src/i18n/locales/en/common.json`~~ — Same as above
- `client/src/i18n/locales/de/settings.json` — German translations for VpnManagement strings (component uses `useTranslation('settings')`)
- `client/src/i18n/locales/en/settings.json` — English translations for VpnManagement strings

### Backend
- `backend/app/services/mobile.py` — Add `vpn_fallback` flag logic and pass to response
- `backend/app/schemas/mobile.py` — Add `vpn_fallback` field to `MobileRegistrationToken`

### Tests
- Update any backend tests asserting on the `MobileRegistrationToken` schema or `generate_registration_token()` return value to account for the new `vpn_fallback` field

## Out of Scope

- Removing any WireGuard server code or endpoints
- Changing VPN routing behavior
- Database migrations
- Modifying the BaluApp (Android) side
- Changing the VPN tab label in SystemControlPage
