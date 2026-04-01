# VPN Page Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify VPN page to use VPN Profile CRUD instead of FritzBox-specific upload, fix dark theme styling and missing i18n keys.

**Architecture:** Remove FritzBox-specific UI from VpnManagement, integrate existing VPNProfileForm + VPNProfileList components with dark theme styling. Backend unchanged.

**Tech Stack:** React, TypeScript, Tailwind CSS, react-i18next

**Spec:** `docs/superpowers/specs/2026-04-01-vpn-page-unification-design.md`

---

### Task 1: Add missing i18n keys (DE + EN)

**Files:**
- Modify: `client/src/i18n/locales/de/remoteServers.json`
- Modify: `client/src/i18n/locales/en/remoteServers.json`

- [ ] **Step 1: Add missing German keys**

In `client/src/i18n/locales/de/remoteServers.json`, add the following:

1. At **root level**, add `"common"` object (needed for `t('common.cancel')` in VPNProfileForm):

```json
{
  "common": {
    "cancel": "Abbrechen"
  },
  "title": "Remote-Server",
  ...existing root keys...
}
```

2. Inside the `"vpn"` object, add missing keys (after the existing `"export"` block):

```json
{
  "vpn": {
    "title": "VPN-Profile",
    "description": "VPN-Konfigurationen für sichere Verbindungen hochladen und verwalten",
    "noProfiles": "Keine VPN-Profile",
    "noProfilesDescription": "Füge ein VPN-Profil hinzu, um sichere Verbindungen zu deinen Servern herzustellen.",
    "created": "Erstellt",
    "updated": "Aktualisiert",
    "deleteConfirm": "VPN-Profil \"{{name}}\" wirklich löschen?",
    "validate": "Validieren",
    "validateConfig": "Konfiguration validieren",
    "deleteProfile": "Profil löschen",
    "addProfile": "VPN-Profil hinzufügen",
    "addProfileDescription": "Lade eine VPN-Konfigurationsdatei hoch, um ein neues Profil zu erstellen.",
    "profileName": "Profilname",
    "profileNamePlaceholder": "z.B. Büro-VPN",
    "type": "VPN-Typ",
    "descriptionPlaceholder": "Optionale Beschreibung...",
    "configFile": "Konfigurationsdatei",
    "clickToUploadConfig": "Klicken, um Konfigurationsdatei hochzuladen (.ovpn, .conf)",
    "certificate": "Zertifikat",
    "clickToUploadCert": "Klicken, um Zertifikat hochzuladen (.crt, .pem)",
    "privateKey": "Privater Schlüssel",
    "clickToUploadKey": "Klicken, um privaten Schlüssel hochzuladen (.key, .pem)",
    "autoConnect": "Automatisch verbinden beim Start",
    "createProfile": "Profil erstellen",
    "export": {
      ...existing export keys...
    }
  }
}
```

Note: The key `"description"` in VPNProfileForm maps to `t('vpn.description')`. Since `"description"` already exists at the `vpn` level (for the section subtitle), rename the form field key. Check VPNProfileForm line 134: it uses `t('vpn.description')` as a form label. This conflicts with the existing `vpn.description` (section subtitle). The form label and section subtitle have different meanings but the same key. **Resolution**: Keep `vpn.description` as the section subtitle (already exists). In VPNProfileForm, the `t('vpn.description')` call at line 134 is used as a form field label meaning "Description" — this is the same word, just used in a different context. Since i18n returns the same text either way ("Beschreibung" / "Description"), the overlap is harmless. No rename needed.

Also: VPNProfileForm line 260 uses `t('common.cancel')`. With `useTranslation('remoteServers')`, this resolves to `remoteServers:common.cancel` (a nested key `common.cancel` inside remoteServers namespace), not the `common` namespace. Add `"common": { "cancel": "Abbrechen" }` to remoteServers.json to fix this.

- [ ] **Step 2: Add missing English keys**

In `client/src/i18n/locales/en/remoteServers.json`, add:

1. At **root level**: `"common": { "cancel": "Cancel" }`

2. Inside the `"vpn"` object, add missing keys:

```json
{
  "common": { "cancel": "Cancel" },
  "vpn": {
    "title": "VPN Profiles",
    "description": "Upload and manage VPN configurations for secure connections",
    "noProfiles": "No VPN Profiles",
    "noProfilesDescription": "Add a VPN profile to establish secure connections to your servers.",
    "created": "Created",
    "updated": "Updated",
    "deleteConfirm": "Delete VPN profile \"{{name}}\"?",
    "validate": "Validate",
    "validateConfig": "Validate configuration",
    "deleteProfile": "Delete profile",
    "addProfile": "Add VPN Profile",
    "addProfileDescription": "Upload a VPN configuration file to create a new profile.",
    "profileName": "Profile Name",
    "profileNamePlaceholder": "e.g. Office VPN",
    "type": "VPN Type",
    "descriptionPlaceholder": "Optional description...",
    "configFile": "Configuration File",
    "clickToUploadConfig": "Click to upload configuration file (.ovpn, .conf)",
    "certificate": "Certificate",
    "clickToUploadCert": "Click to upload certificate (.crt, .pem)",
    "privateKey": "Private Key",
    "clickToUploadKey": "Click to upload private key (.key, .pem)",
    "autoConnect": "Auto-connect on startup",
    "createProfile": "Create Profile",
    "cancel": "Cancel",
    "export": {
      ...existing export keys...
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/i18n/locales/de/remoteServers.json client/src/i18n/locales/en/remoteServers.json
git commit -m "feat(i18n): add missing VPN profile translation keys (de + en)"
```

---

### Task 2: Restyle VPNProfileList to dark theme

**Files:**
- Modify: `client/src/components/RemoteServers/VPNProfileList.tsx`

- [ ] **Step 1: Update empty state styling**

In `VPNProfileList.tsx` lines 81-92, change the empty state from light to dark theme:

```tsx
// BEFORE (light theme)
<div className="flex flex-col items-center justify-center py-12 px-4">
  <div className="text-center max-w-md">
    <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
      <ChevronRight className="w-6 h-6 text-gray-400" />
    </div>
    <h3 className="text-lg font-medium text-gray-900 mb-2">{t('vpn.noProfiles')}</h3>
    <p className="text-sm text-gray-600">
      {t('vpn.noProfilesDescription')}
    </p>
  </div>
</div>

// AFTER (dark theme)
<div className="flex flex-col items-center justify-center py-12 px-4">
  <div className="text-center max-w-md">
    <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-4">
      <ChevronRight className="w-6 h-6 text-slate-500" />
    </div>
    <h3 className="text-lg font-medium text-white mb-2">{t('vpn.noProfiles')}</h3>
    <p className="text-sm text-slate-400">
      {t('vpn.noProfilesDescription')}
    </p>
  </div>
</div>
```

- [ ] **Step 2: Update profile card styling**

In `VPNProfileList.tsx` lines 99-169, change profile cards from light to dark theme:

```tsx
// BEFORE
<div
  key={profile.id}
  className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
>
  {/* Profile Header */}
  <div className="flex items-start justify-between mb-3">
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 mb-1">
        <h3 className="text-base font-semibold text-gray-900 truncate">{profile.name}</h3>

// AFTER
<div
  key={profile.id}
  className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 hover:border-slate-600 transition-colors"
>
  {/* Profile Header */}
  <div className="flex items-start justify-between mb-3">
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 mb-1">
        <h3 className="text-base font-semibold text-white truncate">{profile.name}</h3>
```

Update description text (line 119):
```tsx
// BEFORE
<p className="text-sm text-gray-600">{profile.description}</p>

// AFTER
<p className="text-sm text-slate-400">{profile.description}</p>
```

Update dates section (lines 125-128):
```tsx
// BEFORE
<div className="mb-3 text-xs text-gray-500 space-y-1">

// AFTER
<div className="mb-3 text-xs text-slate-500 space-y-1">
```

Update action buttons (lines 131-168):
```tsx
// Export button - BEFORE
className="flex items-center gap-2 px-3 py-2 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"

// Export button - AFTER
className="flex items-center gap-2 px-3 py-2 text-sm bg-sky-500/20 text-sky-400 rounded hover:bg-sky-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"

// Validate button - BEFORE
className="flex items-center gap-2 px-3 py-2 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"

// Validate button - AFTER
className="flex items-center gap-2 px-3 py-2 text-sm bg-slate-700 text-slate-300 rounded hover:bg-slate-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"

// Delete button - BEFORE
className="ml-auto flex items-center gap-2 px-3 py-2 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"

// Delete button - AFTER
className="ml-auto flex items-center gap-2 px-3 py-2 text-sm bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
```

- [ ] **Step 3: Commit**

```bash
git add client/src/components/RemoteServers/VPNProfileList.tsx
git commit -m "fix(vpn): restyle VPNProfileList to dark theme"
```

---

### Task 3: Restyle VPNProfileForm to dark theme

**Files:**
- Modify: `client/src/components/RemoteServers/VPNProfileForm.tsx`

Note: The `t('common.cancel')` bug is fixed by the `"common": { "cancel": "..." }` root-level key added in Task 1. No code change needed in VPNProfileForm.

- [ ] **Step 1: Update trigger button styling**

In `VPNProfileForm.tsx` lines 71-77:

```tsx
// BEFORE
<button
  onClick={() => setOpen(true)}
  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
  disabled={isLoading}
>
  <Plus className="w-4 h-4" />
  {t('vpn.addProfile')}
</button>

// AFTER
<button
  onClick={() => setOpen(true)}
  className="flex items-center gap-2 px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
  disabled={isLoading}
>
  <Plus className="w-4 h-4" />
  {t('vpn.addProfile')}
</button>
```

- [ ] **Step 2: Update modal styling**

In `VPNProfileForm.tsx` lines 80-94, update the modal wrapper and header:

```tsx
// BEFORE
<div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto">
  <div className="bg-white rounded-lg shadow-lg w-full max-w-md my-8">
    {/* Header */}
    <div className="flex items-center justify-between border-b px-6 py-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">{t('vpn.addProfile')}</h2>
        <p className="text-sm text-gray-600 mt-1">{t('vpn.addProfileDescription')}</p>
      </div>
      <button
        onClick={() => setOpen(false)}
        className="text-gray-400 hover:text-gray-600"
      >

// AFTER
<div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 overflow-y-auto">
  <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-lg w-full max-w-md my-8">
    {/* Header */}
    <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
      <div>
        <h2 className="text-lg font-semibold text-white">{t('vpn.addProfile')}</h2>
        <p className="text-sm text-slate-400 mt-1">{t('vpn.addProfileDescription')}</p>
      </div>
      <button
        onClick={() => setOpen(false)}
        className="text-slate-400 hover:text-slate-200"
      >
```

- [ ] **Step 3: Update form fields styling**

All form labels (lines 100, 117, 134, 149, 174, 210):
```tsx
// BEFORE
className="block text-sm font-medium text-gray-700 mb-1"
// AFTER
className="block text-sm font-medium text-slate-300 mb-1"
```

All text inputs (lines 103, 140):
```tsx
// BEFORE
className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
// AFTER
className="w-full px-3 py-2 border border-slate-700 bg-slate-800 text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
```

Select input (lines 121-123):
```tsx
// BEFORE
className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
// AFTER
className="w-full px-3 py-2 border border-slate-700 bg-slate-800 text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
```

File upload drop zones (lines 151-153, 180, 215):
```tsx
// BEFORE
className="border-2 border-dashed border-gray-300 rounded-lg p-4 cursor-pointer hover:border-blue-500 hover:bg-blue-50 transition-colors"
// AFTER
className="border-2 border-dashed border-slate-600 rounded-lg p-4 cursor-pointer hover:border-sky-500 hover:bg-sky-500/10 transition-colors"
```

File upload text spans:
```tsx
// BEFORE
className="text-sm text-gray-600"
// and
className="text-sm text-gray-600 flex items-center gap-2"
// AFTER
className="text-sm text-slate-400"
// and
className="text-sm text-slate-400 flex items-center gap-2"
```

Upload icon color:
```tsx
// BEFORE
<Upload className="w-4 h-4 text-gray-400" />
// AFTER
<Upload className="w-4 h-4 text-slate-500" />
```

X buttons for clearing files:
```tsx
// BEFORE
className="w-4 h-4 cursor-pointer text-gray-400 hover:text-red-500"
// AFTER
className="w-4 h-4 cursor-pointer text-slate-500 hover:text-red-400"
```

Checkbox (line 242):
```tsx
// BEFORE
className="w-4 h-4 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 cursor-pointer"
// AFTER
className="w-4 h-4 border border-slate-600 rounded focus:ring-2 focus:ring-sky-500 bg-slate-800 cursor-pointer"
```

Checkbox label (line 249):
```tsx
// BEFORE
className="text-sm text-gray-700 cursor-pointer"
// AFTER
className="text-sm text-slate-300 cursor-pointer"
```

- [ ] **Step 4: Update form buttons styling**

Cancel button (lines 256-260):
```tsx
// BEFORE
className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
// AFTER
className="flex-1 px-4 py-2 border border-slate-600 text-slate-300 rounded-lg hover:bg-slate-800 transition-colors"
```

Submit button (lines 261-268):
```tsx
// BEFORE
className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
// AFTER
className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
```

- [ ] **Step 5: Commit**

```bash
git add client/src/components/RemoteServers/VPNProfileForm.tsx
git commit -m "fix(vpn): restyle VPNProfileForm to dark theme"
```

---

### Task 4: Rewrite VpnManagement — remove FritzBox, add VPN Profile CRUD

**Files:**
- Modify: `client/src/components/VpnManagement.tsx`

- [ ] **Step 1: Replace the entire component**

Replace `VpnManagement.tsx` with the following. This removes all FritzBox-specific logic (upload, config display, QR download) and replaces it with VPN Profile CRUD + NAS VPN status.

```tsx
import { useState, useEffect } from 'react';
import { Wifi, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../lib/api';
import { useVPNProfiles } from '../hooks/useRemoteServers';
import { VPNProfileList } from './RemoteServers/VPNProfileList';
import { VPNProfileForm } from './RemoteServers/VPNProfileForm';

export default function VpnManagement() {
  const { t } = useTranslation('settings');
  const vpnProfiles = useVPNProfiles();
  const [nasVpnInfo, setNasVpnInfo] = useState<{ configured: boolean; activeClients: number } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadNasVpnStatus();
  }, []);

  const loadNasVpnStatus = async () => {
    try {
      setLoading(true);
      const serverRes = await apiClient.get('/api/vpn/server-config');
      setNasVpnInfo({
        configured: true,
        activeClients: serverRes.data.active_clients ?? 0,
      });
    } catch {
      setNasVpnInfo({ configured: false, activeClients: 0 });
    } finally {
      setLoading(false);
    }
  };

  if (loading && vpnProfiles.loading) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500 mx-auto"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* VPN Profiles Section */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">VPN Profiles</h3>
          <VPNProfileForm
            onCreateProfile={vpnProfiles.createProfile}
            isLoading={vpnProfiles.loading}
          />
        </div>

        {vpnProfiles.error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300">
            {vpnProfiles.error}
          </div>
        )}

        <VPNProfileList
          profiles={vpnProfiles.profiles}
          isLoading={vpnProfiles.loading}
          onDelete={vpnProfiles.deleteProfile}
          onTestConnection={vpnProfiles.testConnection}
        />
      </div>

      {/* NAS VPN Server Info */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
          <Wifi className="w-5 h-5 mr-2 text-slate-400" />
          {t('vpn.nasVpnTitle')}
        </h3>

        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg mb-4">
          <p className="text-xs text-amber-300">
            {t('vpn.nasVpnWolWarning')}
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
    </div>
  );
}
```

Key changes:
- Removed: `Upload, Trash2, Check, AlertCircle, Download` icon imports
- Removed: `Trans` import from react-i18next
- Removed: `getApiErrorMessage` import
- Removed: All FritzBox state (`config`, `uploadFile`, `publicEndpoint`, `uploading`, `error`, `success`, `qrData`)
- Removed: `loadConfig()`, `handleFileSelect()`, `handleUpload()`, `handleDelete()`, `downloadConfig()`
- Removed: FritzBox upload section, active config display, no-config info section
- Added: `VPNProfileForm` import and rendered in profiles header
- Kept: `useVPNProfiles` hook, `VPNProfileList`, NAS VPN status section

- [ ] **Step 2: Commit**

```bash
git add client/src/components/VpnManagement.tsx
git commit -m "feat(vpn): unify VPN page with profile CRUD, remove FritzBox upload UI"
```

---

### Task 5: Verify and final commit

- [ ] **Step 1: Run frontend build to check for compile errors**

```bash
cd client && npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 2: Run frontend lint**

```bash
cd client && npm run lint
```

Expected: No new lint errors.

- [ ] **Step 3: Verify dev mode works**

```bash
cd .. && python start_dev.py
```

Open `http://localhost:5173/vpn` in browser. Verify:
- "VPN Profiles" section shows with "Add VPN Profile" button
- Empty state shows translated text (not raw i18n keys)
- Clicking "Add VPN Profile" opens dark-themed modal
- NAS VPN Server section shows below

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(vpn): address build/lint issues from VPN page unification"
```

Only if Step 1 or Step 2 revealed issues that needed fixing.
