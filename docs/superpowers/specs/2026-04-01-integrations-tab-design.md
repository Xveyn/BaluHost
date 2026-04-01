# Integrations Tab in Settings

**Date:** 2026-04-01
**Status:** Approved

## Summary

Move OAuth/credential configuration from the CloudConnectWizard into a new "Integrations" tab on the Settings page. Each cloud provider gets a persistent card showing configuration status, capabilities (Import / Export), and actions. The CloudConnectWizard no longer handles inline OAuth setup — it redirects unconfigured users to Settings > Integrations.

## Providers & Capabilities

| Provider     | Auth Type   | Cloud Import | Cloud Export (Externes Teilen) |
|-------------|-------------|--------------|-------------------------------|
| Google Drive | OAuth       | yes          | yes                           |
| OneDrive     | OAuth       | yes          | yes                           |
| iCloud       | Credentials | yes          | no (display "Nur Import")     |

## Design Decisions

- **Per-user credentials** — every user configures their own OAuth client IDs (not system-wide). Admins can view all users' configs.
- **iCloud stays in CloudConnectWizard** — iCloud uses session-based Apple ID login + 2FA, which expires and must be re-authenticated. This is a "connect" action, not a one-time credential setup.
- **CloudConnectWizard simplification** — the `configure` step is removed. Unconfigured OAuth providers show a hint with link to `/settings?tab=integrations`.

## Frontend Changes

### 1. SettingsPage.tsx

- Add `'integrations'` to the `SettingsTab` union type and `validTabs` array
- Add tab button with `Plug` icon from lucide-react (placed after Notifications, before API Keys)
- Render `<IntegrationsTab />` when active

### 2. New: IntegrationsTab.tsx (`client/src/components/settings/IntegrationsTab.tsx`)

Displays one card per provider:

**Card contents:**
- Provider icon (gradient circle with initials, matching CloudConnectWizard style)
- Provider name
- Capability badges: "Cloud Import" (always), "Cloud Export" (Google Drive, OneDrive only)
- iCloud: additional hint "Nur Import — Login erfolgt beim Verbinden"
- Status indicator: configured (green) / not configured (gray)
- Client ID hint when configured (e.g., `1234...5678`) with source label `(env)` or `(eigene)`
- Actions: "Konfigurieren" button (unconfigured) / "Löschen" button (configured, DB-only)

**OAuth configuration flow (Google Drive / OneDrive):**
- Clicking "Konfigurieren" opens an inline form (or small modal) with Client ID + Client Secret fields
- Saves via existing `PUT /api/cloud/oauth-config`
- Deletes via existing `DELETE /api/cloud/oauth-config/{provider}`

**Admin view:**
- Admins see an additional section listing other users' configured integrations (read-only overview)
- Uses new endpoint `GET /api/cloud/oauth-configs/all`

**Normal user view:**
- Only sees own configurations

### 3. CloudConnectWizard.tsx changes

- Remove the `'configure'` step entirely (and related state: `configProvider`, `clientId`, `clientSecret`, `handleSaveConfig`)
- Remove `PROVIDER_HELP` constant
- When `handleSelectProvider` is called for an unconfigured OAuth provider: instead of entering the configure step, show a message: "Bitte zuerst in Settings > Integrations konfigurieren" with a link/button navigating to `/settings?tab=integrations`
- iCloud flow remains unchanged

### 4. i18n

- Add translation keys under `settings` namespace for the new tab and card labels

## Backend Changes

### New endpoint: `GET /api/cloud/oauth-configs/all` (Admin only)

Returns all users' OAuth configurations (for admin overview).

```python
@router.get("/oauth-configs/all")
@user_limiter.limit(get_limit("admin_operations"))
async def list_all_oauth_configs(
    request: Request, response: Response,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """List all OAuth configs across users (admin only)."""
```

Response: list of `{ provider, user_id, username, is_configured, client_id_hint, source, updated_at }`

### CloudOAuthConfigService addition

New method `get_all_configs(db)` that returns all DB-stored configs with associated usernames.

### Existing endpoints (no changes needed)

- `PUT /api/cloud/oauth-config` — save credentials (per-user)
- `DELETE /api/cloud/oauth-config/{provider}` — delete credentials (per-user)
- `GET /api/cloud/providers` — provider status (already returns `configured` + `auth_type`)

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/components/settings/IntegrationsTab.tsx` | New integrations tab component |

## Files to Modify

| File | Change |
|------|--------|
| `client/src/pages/SettingsPage.tsx` | Add integrations tab |
| `client/src/components/cloud/CloudConnectWizard.tsx` | Remove configure step, add redirect hint |
| `backend/app/api/routes/cloud.py` | Add admin endpoint for listing all configs |
| `backend/app/services/cloud/oauth_config.py` | Add `get_all_configs()` method |
| `client/src/api/cloud-import.ts` | Add `getAllOAuthConfigs()` function |
| `client/src/i18n/locales/en/settings.json` | Add integration tab translations |
| `client/src/i18n/locales/de/settings.json` | Add integration tab translations |

## Out of Scope

- Changing how iCloud login works (stays in wizard)
- Adding new cloud providers
- Changing the OAuth flow itself (redirect-based, unchanged)
- Cloud export configuration (uses same connections, no separate setup needed)
