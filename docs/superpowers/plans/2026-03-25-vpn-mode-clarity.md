# VPN Mode Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clearly distinguish Router-VPN (FritzBox) from NAS-VPN (WireGuard Server) in the UI and warn about WoL incompatibility.

**Architecture:** Backend adds a `vpn_fallback` boolean to the mobile token response. Frontend relabels VPN type buttons, adds WoL warnings in the token generation form, QR dialog, and VPN management page. No routing/logic changes — both VPN paths stay functional.

**Tech Stack:** Python/FastAPI (backend schema), React/TypeScript/Tailwind (frontend), i18n JSON files

**Spec:** `docs/superpowers/specs/2026-03-25-vpn-mode-clarity-design.md`

---

### Task 1: Backend — Add `vpn_fallback` to schema and service

**Files:**
- Modify: `backend/app/schemas/mobile.py:63-71`
- Modify: `backend/app/services/mobile.py:69-171`
- Modify: `backend/tests/integration/test_mobile_token_vpn_flow.py`

- [ ] **Step 1: Add `vpn_fallback` field to `MobileRegistrationToken` schema**

In `backend/app/schemas/mobile.py`, add the field to the `MobileRegistrationToken` class (after line 70):

```python
vpn_fallback: bool = Field(default=False, description="True when auto mode fell back to NAS-VPN")
```

- [ ] **Step 2: Add `vpn_fallback` logic to `generate_registration_token()`**

In `backend/app/services/mobile.py`, add a tracking variable after line 71 (`vpn_config_type = None`):

```python
vpn_did_fallback = False
```

Then inside the `auto` branch (after line 92, `use_wireguard = True`), add:

```python
vpn_did_fallback = True
```

Finally, update the return statement at line 164-171 to include the new field:

```python
return MobileRegistrationTokenSchema(
    token=token,
    server_url=server_url,
    expires_at=expires_at,
    qr_code=qr_code_base64,
    vpn_config=vpn_config_base64,
    device_token_validity_days=token_validity_days,
    vpn_fallback=vpn_did_fallback and vpn_config_base64 is not None,
)
```

The `and vpn_config_base64 is not None` ensures `vpn_fallback` is only `True` when the fallback actually succeeded (VPN config was generated).

- [ ] **Step 3: Update existing test to verify `vpn_fallback`**

In `backend/tests/integration/test_mobile_token_vpn_flow.py`, after line 41 (`assert data.get("vpn_config") is not None`), add:

```python
# Default vpn_type is "auto" and no FritzBox config exists in test DB,
# so it falls back to NAS-VPN (WireGuard) — vpn_fallback should be True
assert data.get("vpn_fallback") is True
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/integration/test_mobile_token_vpn_flow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/mobile.py backend/app/services/mobile.py backend/tests/integration/test_mobile_token_vpn_flow.py
git commit -m "feat(vpn): add vpn_fallback flag to mobile token response"
```

---

### Task 2: Frontend — Add `vpn_fallback` to TypeScript interface

**Files:**
- Modify: `client/src/api/mobile.ts:7-14`

- [ ] **Step 1: Add `vpn_fallback` to `MobileRegistrationToken` interface**

In `client/src/api/mobile.ts`, add after line 12 (`vpn_config?: string;`):

```typescript
vpn_fallback?: boolean;
```

- [ ] **Step 2: Commit**

```bash
git add client/src/api/mobile.ts
git commit -m "feat(vpn): add vpn_fallback to MobileRegistrationToken type"
```

---

### Task 3: Frontend — Relabel VPN type buttons and add WoL warnings in MobileDevicesPage

> **Note:** MobileDevicesPage currently hardcodes all UI strings in German (no i18n `t()` calls). This plan follows the existing pattern. i18n for this page is out of scope.

**Files:**
- Modify: `client/src/pages/MobileDevicesPage.tsx:208-253` (VPN type selector)
- Modify: `client/src/pages/MobileDevicesPage.tsx:469-476` (QR dialog VPN info)

- [ ] **Step 1: Update VPN type button labels and descriptions**

In `client/src/pages/MobileDevicesPage.tsx`, replace lines 228-251 (the button array and description paragraph) with:

```tsx
{[
  { value: 'auto', label: 'Automatisch' },
  ...(availableVpnTypes.includes('fritzbox') ? [{ value: 'fritzbox', label: 'Router-VPN (FritzBox)' }] : []),
  { value: 'wireguard', label: 'NAS-VPN (WireGuard)' },
].map((opt) => (
  <button
    key={opt.value}
    type="button"
    onClick={() => setVpnType(opt.value)}
    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
      vpnType === opt.value
        ? 'border-sky-500 bg-sky-500/20 text-sky-300'
        : 'border-slate-700 bg-slate-800 text-slate-400 hover:border-slate-600'
    }`}
  >
    {opt.label}
  </button>
))}
</div>
<p className="text-xs text-slate-500">
  {vpnType === 'auto' && 'Router-VPN bevorzugt, NAS-VPN als Fallback'}
  {vpnType === 'fritzbox' && 'Nutzt die vom Admin hochgeladene Router-Konfiguration'}
  {vpnType === 'wireguard' && 'VPN laeuft direkt ueber das NAS'}
</p>
```

- [ ] **Step 2: Add WoL warning when NAS-VPN is selected**

Directly after the description `<p>` above (still inside the `{includeVpn && availableVpnTypes.length > 1 && (` block, before its closing `</div>` and `)}` on line 252-253), add:

```tsx
{vpnType === 'wireguard' && (
  <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
    <p className="text-xs text-amber-300">
      ⚠ VPN laeuft direkt ueber das NAS. Bei Nutzung von Sleep/WoL ist der VPN-Tunnel nicht erreichbar, solange das NAS schlaeft.
    </p>
  </div>
)}
```

- [ ] **Step 3: Add proactive WoL warning when only NAS-VPN is available**

After the VPN type selector block (after the `{includeVpn && availableVpnTypes.length > 1 && (...)}`), add a new block for the case when only WireGuard is available (the selector is hidden but the user still checked "VPN einschliessen"):

```tsx
{includeVpn && availableVpnTypes.length === 1 && availableVpnTypes[0] === 'wireguard' && (
  <div className="ml-6 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
    <p className="text-xs text-amber-300">
      ⚠ Kein Router-VPN konfiguriert. VPN wird direkt ueber das NAS bereitgestellt. Bei Nutzung von Sleep/WoL ist der VPN-Tunnel nicht erreichbar, solange das NAS schlaeft.
    </p>
  </div>
)}
```

- [ ] **Step 4: Add fallback warning in QR dialog**

In `MobileDevicesPage.tsx`, find the QR dialog section around line 473-475 where VPN config is confirmed:

```tsx
{qrData.vpn_config && (
  <p className="text-green-400">✓ VPN-Konfiguration eingeschlossen</p>
)}
```

Replace with:

```tsx
{qrData.vpn_config && (
  <p className="text-green-400">✓ VPN-Konfiguration eingeschlossen</p>
)}
{qrData.vpn_fallback && (
  <div className="p-2 bg-amber-500/10 border border-amber-500/30 rounded-lg">
    <p className="text-xs text-amber-300">
      ⚠ Kein Router-VPN konfiguriert — NAS-VPN wird als Fallback verwendet.
    </p>
  </div>
)}
```

- [ ] **Step 5: Verify visually**

Run: `cd client && npm run dev`

Check at `http://localhost:5173`:
1. Go to Mobile Devices page
2. Check "VPN-Konfiguration einschliessen"
3. Verify new button labels: "Automatisch", "Router-VPN (FritzBox)", "NAS-VPN (WireGuard)"
4. Select "NAS-VPN (WireGuard)" — amber warning should appear
5. If no FritzBox config is uploaded, the proactive warning should show when only the checkbox is checked

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/MobileDevicesPage.tsx
git commit -m "feat(vpn): relabel VPN types and add WoL warnings in mobile page"
```

---

### Task 4: Frontend — Add NAS-VPN info section to VpnManagement

**Files:**
- Modify: `client/src/components/VpnManagement.tsx:270-285`
- Modify: `client/src/i18n/locales/de/settings.json:261-289`
- Modify: `client/src/i18n/locales/en/settings.json:261-289`

- [ ] **Step 1: Add NAS-VPN server status state and fetch**

In `client/src/components/VpnManagement.tsx`, add state after the existing state declarations (around line 24, after `qrData`):

```tsx
const [nasVpnInfo, setNasVpnInfo] = useState<{ configured: boolean; activeClients: number } | null>(null);
```

In the `loadConfig` function (around line 30), after the FritzBox config loading, add:

> **Note:** `/api/vpn/server-config` is admin-only (returns 403 for non-admin users). This is acceptable because VpnManagement is only rendered in the admin-accessible System Control page. The `catch` block handles any 403 gracefully.

```tsx
// Load NAS-VPN server status (admin-only endpoint)
try {
  const serverRes = await apiClient.get('/api/vpn/server-config');
  setNasVpnInfo({
    configured: true,
    activeClients: serverRes.data.active_clients ?? 0,
  });
} catch {
  setNasVpnInfo({ configured: false, activeClients: 0 });
}
```

- [ ] **Step 2: Add NAS-VPN info section in the render**

Before the closing `</div>` of the component (line 283), add:

```tsx
{/* NAS-VPN Info Section */}
<div className="card border-slate-800/60 bg-slate-900/55">
  <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
    <Wifi className="w-5 h-5 mr-2 text-slate-400" />
    {t('vpn.nasVpnTitle')}
  </h3>

  <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg mb-4">
    <p className="text-xs text-amber-300">
      ⚠ {t('vpn.nasVpnWolWarning')}
    </p>
  </div>

  {nasVpnInfo && (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
      <div>
        <span className="text-slate-400">{t('vpn.status')}:</span>
        <p className={`font-medium ${nasVpnInfo.configured ? 'text-green-400' : 'text-slate-400'}`}>
          {nasVpnInfo.configured ? t('vpn.nasVpnInitialized') : t('vpn.nasVpnNotInitialized')}
        </p>
      </div>
      {nasVpnInfo.configured && (
        <div>
          <span className="text-slate-400">{t('vpn.nasVpnActiveClients')}:</span>
          <p className="text-white font-medium">{nasVpnInfo.activeClients}</p>
        </div>
      )}
    </div>
  )}
</div>
```

- [ ] **Step 3: Add i18n keys to German settings.json**

In `client/src/i18n/locales/de/settings.json`, add the following keys inside the `"vpn"` object (after `"downloadFailed"` on line 289):

```json
"nasVpnTitle": "NAS-VPN (WireGuard Server)",
"nasVpnWolWarning": "Wenn das NAS per Sleep/WoL in den Ruhezustand versetzt wird, ist der NAS-VPN-Tunnel nicht erreichbar. Fuer unterbrechungsfreien VPN-Zugang wird Router-VPN empfohlen.",
"nasVpnInitialized": "Initialisiert",
"nasVpnNotInitialized": "Nicht initialisiert",
"nasVpnActiveClients": "Aktive Clients"
```

- [ ] **Step 4: Add i18n keys to English settings.json**

In `client/src/i18n/locales/en/settings.json`, add the same keys inside the `"vpn"` object (after `"downloadFailed"` on line 289):

```json
"nasVpnTitle": "NAS-VPN (WireGuard Server)",
"nasVpnWolWarning": "When the NAS is suspended via Sleep/WoL, the NAS-VPN tunnel will be unreachable. For uninterrupted VPN access, Router-VPN is recommended.",
"nasVpnInitialized": "Initialized",
"nasVpnNotInitialized": "Not initialized",
"nasVpnActiveClients": "Active clients"
```

- [ ] **Step 5: Verify visually**

Run: `cd client && npm run dev`

Check at `http://localhost:5173`:
1. Go to System Control > Network > VPN
2. Below the FritzBox section, the new "NAS-VPN (WireGuard Server)" card should appear
3. Amber WoL warning is always visible
4. Status shows "Nicht initialisiert" or "Initialisiert" + active client count

- [ ] **Step 6: Commit**

```bash
git add client/src/components/VpnManagement.tsx client/src/i18n/locales/de/settings.json client/src/i18n/locales/en/settings.json
git commit -m "feat(vpn): add NAS-VPN info section with WoL warning to VPN management page"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run backend tests**

Run: `cd backend && python -m pytest tests/ -k "mobile" -v`
Expected: All mobile-related tests PASS

- [ ] **Step 2: Run frontend build**

Run: `cd client && npm run build`
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 3: Commit any remaining changes**

If all clean, no further commit needed.
