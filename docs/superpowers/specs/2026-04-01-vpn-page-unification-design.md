# VPN Page Unification

**Date**: 2026-04-01
**Status**: Approved

## Problem

The VPN page (`VpnManagement.tsx`) has three separate VPN-related systems displayed together:

1. **FritzBox Upload** — uploads `.conf` to `/api/vpn/fritzbox/upload`, stored in `fritzbox_vpn_configs` table
2. **VPN Profiles** — CRUD via `/api/vpn-profiles`, stored in `vpn_profiles` table
3. **NAS VPN Server** — read-only status from `/api/vpn/server-config`

Users expect a single upload mechanism. Uploading a FritzBox config does not create a VPN Profile, so the "VPN Profiles" section always shows empty. Additionally:

- Missing i18n keys cause raw keys (`vpn.noProfilesDescription`) to display
- `VPNProfileList` and `VPNProfileForm` use light-theme styling on a dark-theme page
- No VPN Profile creation form exists on the VPN page (only on Remote Servers page)

## Solution

Unify the upload UX: replace the FritzBox-specific upload section and config display with the existing VPN Profile CRUD system. Backend stays unchanged.

## Design

### VPN Page Layout (top to bottom)

1. **VPN Profiles section** — header with "VPN Profiles" title + "Add" button (opens `VPNProfileForm` modal)
   - Profile list: cards with name, type badge, auto-connect indicator, dates, action buttons (Export/QR, Validate, Delete)
   - Empty state: translated text with description
2. **NAS VPN Server section** — unchanged (Status, Active Clients, WoL warning)

### Removed from VPN Page

- FritzBox `.conf` upload form (file input, public endpoint input, upload button)
- FritzBox active config display (endpoint, DNS, status, QR download)
- All FritzBox-related state and API calls (`/api/vpn/fritzbox/*`)

### File Changes

| File | Change |
|------|--------|
| `client/src/components/VpnManagement.tsx` | Remove FritzBox upload section + config display + related state/handlers. Add `VPNProfileForm` import and render it in VPN Profiles section header. |
| `client/src/components/RemoteServers/VPNProfileList.tsx` | Restyle from light theme (`bg-white`, `text-gray-900`, `border-gray-200`) to dark theme (`bg-slate-800/60`, `text-white`, `border-slate-700`) matching existing page components. |
| `client/src/components/RemoteServers/VPNProfileForm.tsx` | Restyle modal from light theme to dark theme matching existing page components. |
| `client/src/i18n/locales/de/remoteServers.json` | Add missing keys: `vpn.noProfiles`, `vpn.noProfilesDescription`, `vpn.created`, `vpn.updated`, `vpn.deleteConfirm`, `vpn.validate`, `vpn.validateConfig`, `vpn.deleteProfile`, plus form keys used by VPNProfileForm (`vpn.addProfile`, `vpn.addProfileDescription`, `vpn.profileName`, `vpn.profileNamePlaceholder`, `vpn.type`, `vpn.description`, `vpn.descriptionPlaceholder`, `vpn.configFile`, `vpn.clickToUploadConfig`, `vpn.certificate`, `vpn.clickToUploadCert`, `vpn.privateKey`, `vpn.clickToUploadKey`, `vpn.autoConnect`, `vpn.createProfile`, `common.cancel`) |
| `client/src/i18n/locales/en/remoteServers.json` | Same missing keys in English |

### Backend

No changes. FritzBox endpoints remain in the backend (unused by frontend after this change). VPN Profile API (`/api/vpn-profiles`) is already fully functional with CRUD, validation, and export.

### No Database Migration

No schema changes. The `vpn_profiles` table is already in production.

## Out of Scope

- Alembic migration of existing `fritzbox_vpn_configs` data to `vpn_profiles`
- Removal of FritzBox VPN backend endpoints/models/services
- Changes to Remote Servers page (keeps its own VPN Profile tab)
- Changes to NAS VPN Server section
