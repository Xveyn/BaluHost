# Integrations Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move OAuth/credential configuration from the CloudConnectWizard into a new "Integrations" tab on the Settings page, with per-provider cards, inline config forms, and admin overview.

**Architecture:** Backend adds one new admin-only endpoint and one service method. Frontend adds an `IntegrationsTab` component to the Settings page and simplifies the CloudConnectWizard by removing inline OAuth configuration. i18n keys added for both EN and DE.

**Tech Stack:** Python/FastAPI, SQLAlchemy, React/TypeScript, Tailwind CSS, react-i18next, lucide-react

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/services/cloud/oauth_config.py` | Add `get_all_configs()` method |
| Modify | `backend/app/schemas/cloud.py` | Add `CloudOAuthConfigAdminResponse` schema |
| Modify | `backend/app/api/routes/cloud.py` | Add admin list endpoint |
| Create | `backend/tests/test_cloud_oauth_admin.py` | Tests for new endpoint |
| Modify | `client/src/api/cloud-import.ts` | Add `getAllOAuthConfigs()` API function |
| Modify | `client/src/i18n/locales/en/settings.json` | Add integrations tab translations |
| Modify | `client/src/i18n/locales/de/settings.json` | Add integrations tab translations |
| Create | `client/src/components/settings/IntegrationsTab.tsx` | New integrations tab component |
| Modify | `client/src/pages/SettingsPage.tsx` | Wire up integrations tab |
| Modify | `client/src/components/cloud/CloudConnectWizard.tsx` | Remove configure step, add redirect |

---

### Task 1: Backend — `get_all_configs()` service method

**Files:**
- Modify: `backend/app/services/cloud/oauth_config.py:16-148`

- [ ] **Step 1: Add `get_all_configs` method to `CloudOAuthConfigService`**

Add this method at the end of the class (before the `_get_config` internal method, around line 132):

```python
def get_all_configs(self) -> list[dict]:
    """
    Return all DB-stored OAuth configs with associated usernames.

    Used by admin endpoint to show an overview of all users' configurations.
    Returns a list of dicts with provider, user_id, username, client_id_hint, updated_at.
    """
    from app.models.user import User

    try:
        rows = (
            self.db.query(CloudOAuthConfig, User.username)
            .join(User, CloudOAuthConfig.user_id == User.id)
            .order_by(User.username, CloudOAuthConfig.provider)
            .all()
        )
    except ProgrammingError:
        self.db.rollback()
        logger.debug("cloud_oauth_configs table not found")
        return []

    results = []
    for config, username in rows:
        hint = None
        try:
            cid = decrypt_credentials(config.encrypted_client_id)
            if len(cid) > 8:
                hint = f"{cid[:4]}...{cid[-4:]}"
            else:
                hint = cid
        except ValueError:
            hint = "(error)"

        results.append({
            "provider": config.provider,
            "user_id": config.user_id,
            "username": username,
            "client_id_hint": hint,
            "updated_at": config.updated_at,
        })

    return results
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/cloud/oauth_config.py
git commit -m "feat(cloud): add get_all_configs method for admin overview"
```

---

### Task 2: Backend — Admin response schema

**Files:**
- Modify: `backend/app/schemas/cloud.py:88-95`

- [ ] **Step 1: Add `CloudOAuthConfigAdminResponse` schema**

Add after the existing `CloudOAuthConfigResponse` class (after line 95):

```python
class CloudOAuthConfigAdminResponse(BaseModel):
    """Admin view of OAuth config for any user."""
    provider: str
    user_id: int
    username: str
    client_id_hint: Optional[str] = None
    updated_at: Optional[datetime] = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/cloud.py
git commit -m "feat(cloud): add admin response schema for OAuth configs"
```

---

### Task 3: Backend — Admin list endpoint

**Files:**
- Modify: `backend/app/api/routes/cloud.py:1-132`

- [ ] **Step 1: Add `get_current_admin` import**

In `cloud.py` line 9, change:

```python
from app.api.deps import get_current_user, get_db
```

to:

```python
from app.api.deps import get_current_admin, get_current_user, get_db
```

- [ ] **Step 2: Add `CloudOAuthConfigAdminResponse` to schema imports**

In the import block (line 13-24), add `CloudOAuthConfigAdminResponse` to the imports from `app.schemas.cloud`:

```python
from app.schemas.cloud import (
    CloudConnectionResponse,
    CloudFileResponse,
    CloudImportJobResponse,
    CloudImportRequest,
    CloudOAuthConfigAdminResponse,
    CloudOAuthConfigCreate,
    CloudOAuthConfigResponse,
    DevConnectRequest,
    ICloud2FARequest,
    ICloudConnectRequest,
    OAuthCallbackRequest,
)
```

- [ ] **Step 3: Add the admin list endpoint**

Add after the existing `delete_oauth_config` endpoint (after line 131), before the `# ─── Connections` section:

```python
@router.get("/oauth-configs/all", response_model=list[CloudOAuthConfigAdminResponse])
@user_limiter.limit(get_limit("admin_operations"))
async def list_all_oauth_configs(
    request: Request, response: Response,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """List all OAuth configs across users (admin only)."""
    svc = CloudOAuthConfigService(db)
    configs = svc.get_all_configs()
    return [CloudOAuthConfigAdminResponse(**c) for c in configs]
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/cloud.py
git commit -m "feat(cloud): add admin endpoint to list all OAuth configs"
```

---

### Task 4: Backend — Tests for admin endpoint

**Files:**
- Create: `backend/tests/test_cloud_oauth_admin.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for the cloud OAuth admin list endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from tests.conftest import get_auth_headers


class TestCloudOAuthAdminEndpoint:
    """Tests for GET /api/cloud/oauth-configs/all."""

    def test_requires_admin(self, client: TestClient, user_headers: dict):
        """Regular users should get 403."""
        resp = client.get(f"{settings.api_prefix}/cloud/oauth-configs/all", headers=user_headers)
        assert resp.status_code == 403

    def test_admin_gets_empty_list(self, client: TestClient, admin_headers: dict):
        """Admin should get an empty list when no configs exist."""
        resp = client.get(f"{settings.api_prefix}/cloud/oauth-configs/all", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_admin_sees_user_config(self, client: TestClient, admin_headers: dict, user_headers: dict):
        """Admin should see configs created by other users."""
        # Create a config as regular user
        client.put(
            f"{settings.api_prefix}/cloud/oauth-config",
            json={"provider": "google_drive", "client_id": "test-id-12345678", "client_secret": "test-secret"},
            headers=user_headers,
        )

        # Admin should see it
        resp = client.get(f"{settings.api_prefix}/cloud/oauth-configs/all", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

        google_config = next((c for c in data if c["provider"] == "google_drive"), None)
        assert google_config is not None
        assert google_config["username"] == "testuser"
        assert google_config["client_id_hint"] is not None

    def test_unauthenticated_gets_401(self, client: TestClient):
        """No auth should get 401."""
        resp = client.get(f"{settings.api_prefix}/cloud/oauth-configs/all")
        assert resp.status_code in (401, 403)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_cloud_oauth_admin.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_cloud_oauth_admin.py
git commit -m "test(cloud): add tests for admin OAuth config listing"
```

---

### Task 5: Frontend — API client function

**Files:**
- Modify: `client/src/api/cloud-import.ts:184-200`

- [ ] **Step 1: Add admin config types and function**

Add after the existing `deleteOAuthConfig` function (after line 199), before the file ends:

```typescript
// ─── Admin: All OAuth Configs ───────────────────────────────

export interface OAuthConfigAdmin {
  provider: CloudProvider;
  user_id: number;
  username: string;
  client_id_hint: string | null;
  updated_at: string | null;
}

export async function getAllOAuthConfigs(): Promise<OAuthConfigAdmin[]> {
  const res = await apiClient.get('/api/cloud/oauth-configs/all');
  return res.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/api/cloud-import.ts
git commit -m "feat(cloud): add getAllOAuthConfigs API client function"
```

---

### Task 6: Frontend — i18n translations

**Files:**
- Modify: `client/src/i18n/locales/en/settings.json`
- Modify: `client/src/i18n/locales/de/settings.json`

- [ ] **Step 1: Add English translations**

In `en/settings.json`, add `"integrations"` to the `"tabs"` object (after the `"notifications"` entry):

```json
"integrations": "Integrations"
```

Then add the `"integrations"` section at the top level (after the `"tapo"` section, before the closing `}`):

```json
"integrations": {
  "title": "Cloud Integrations",
  "description": "Configure cloud provider credentials for importing and sharing files.",
  "cloudImport": "Cloud Import",
  "cloudExport": "Cloud Export",
  "importOnly": "Import only — login via Cloud Import page",
  "configured": "Configured",
  "notConfigured": "Not configured",
  "source": "Source",
  "sourceEnv": "Environment",
  "sourceDb": "Custom",
  "configure": "Configure",
  "delete": "Delete",
  "deleteConfirm": "Remove credentials for {{provider}}? The environment fallback will be used if available.",
  "deleteSuccess": "Credentials deleted",
  "deleteFailed": "Failed to delete credentials",
  "saveSuccess": "Credentials saved",
  "saveFailed": "Failed to save credentials",
  "clientId": "Client ID",
  "clientIdPlaceholder": "e.g. 123456789.apps.googleusercontent.com",
  "clientSecret": "Client Secret",
  "clientSecretPlaceholder": "Client Secret",
  "save": "Save",
  "cancel": "Cancel",
  "adminOverview": "All User Configurations",
  "adminOverviewDescription": "Overview of cloud credentials configured by all users.",
  "noConfigs": "No users have configured cloud credentials yet.",
  "user": "User",
  "provider": "Provider",
  "lastUpdated": "Last Updated",
  "helpGoogle": "Create credentials in the Google Cloud Console under APIs & Services > Credentials.",
  "helpOneDrive": "Register an app in the Azure Portal under App registrations."
}
```

- [ ] **Step 2: Add German translations**

In `de/settings.json`, add `"integrations"` to the `"tabs"` object (after `"notifications"`):

```json
"integrations": "Integrationen"
```

Then add the `"integrations"` section at the top level (after `"tapo"`, before closing `}`):

```json
"integrations": {
  "title": "Cloud-Integrationen",
  "description": "Cloud-Provider-Zugangsdaten fuer Import und Teilen konfigurieren.",
  "cloudImport": "Cloud Import",
  "cloudExport": "Cloud Export",
  "importOnly": "Nur Import — Login ueber Cloud Import Seite",
  "configured": "Konfiguriert",
  "notConfigured": "Nicht konfiguriert",
  "source": "Quelle",
  "sourceEnv": "Umgebungsvariable",
  "sourceDb": "Eigene",
  "configure": "Konfigurieren",
  "delete": "Loeschen",
  "deleteConfirm": "Zugangsdaten fuer {{provider}} entfernen? Falls vorhanden, wird der Umgebungsvariablen-Fallback verwendet.",
  "deleteSuccess": "Zugangsdaten geloescht",
  "deleteFailed": "Fehler beim Loeschen der Zugangsdaten",
  "saveSuccess": "Zugangsdaten gespeichert",
  "saveFailed": "Fehler beim Speichern der Zugangsdaten",
  "clientId": "Client-ID",
  "clientIdPlaceholder": "z.B. 123456789.apps.googleusercontent.com",
  "clientSecret": "Client Secret",
  "clientSecretPlaceholder": "Client Secret",
  "save": "Speichern",
  "cancel": "Abbrechen",
  "adminOverview": "Alle Benutzer-Konfigurationen",
  "adminOverviewDescription": "Uebersicht der Cloud-Zugangsdaten aller Benutzer.",
  "noConfigs": "Noch keine Benutzer haben Cloud-Zugangsdaten konfiguriert.",
  "user": "Benutzer",
  "provider": "Provider",
  "lastUpdated": "Zuletzt aktualisiert",
  "helpGoogle": "Zugangsdaten in der Google Cloud Console unter APIs & Services > Credentials erstellen.",
  "helpOneDrive": "App im Azure Portal unter App-Registrierungen registrieren."
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/i18n/locales/en/settings.json client/src/i18n/locales/de/settings.json
git commit -m "feat(i18n): add integrations tab translations for EN and DE"
```

---

### Task 7: Frontend — IntegrationsTab component

**Files:**
- Create: `client/src/components/settings/IntegrationsTab.tsx`

- [ ] **Step 1: Create the IntegrationsTab component**

```tsx
import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Cloud, KeyRound, Loader2, Trash2, ExternalLink, CheckCircle2,
  XCircle, Info, Users,
} from 'lucide-react';
import {
  getProviders, setOAuthConfig, deleteOAuthConfig, getAllOAuthConfigs,
  type CloudProvider, type ProvidersStatus, type OAuthConfigAdmin,
  PROVIDER_LABELS,
} from '../../api/cloud-import';
import { toast } from 'react-hot-toast';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';

interface IntegrationsTabProps {
  isAdmin: boolean;
}

const PROVIDERS: { id: CloudProvider; gradient: string; icon: string; capabilities: ('import' | 'export')[] }[] = [
  { id: 'google_drive', gradient: 'from-blue-500 to-green-500', icon: 'GD', capabilities: ['import', 'export'] },
  { id: 'onedrive', gradient: 'from-blue-600 to-sky-400', icon: 'OD', capabilities: ['import', 'export'] },
  { id: 'icloud', gradient: 'from-slate-400 to-slate-200', icon: 'iC', capabilities: ['import'] },
];

const PROVIDER_HELP_KEYS: Record<string, string> = {
  google_drive: 'helpGoogle',
  onedrive: 'helpOneDrive',
};

export default function IntegrationsTab({ isAdmin }: IntegrationsTabProps) {
  const { t } = useTranslation('settings');
  const { confirm, dialog } = useConfirmDialog();

  const [providerStatus, setProviderStatus] = useState<ProvidersStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [adminConfigs, setAdminConfigs] = useState<OAuthConfigAdmin[]>([]);

  // Inline config form
  const [configuring, setConfiguring] = useState<CloudProvider | null>(null);
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [status, configs] = await Promise.all([
        getProviders(),
        isAdmin ? getAllOAuthConfigs().catch(() => []) : Promise.resolve([]),
      ]);
      setProviderStatus(status);
      setAdminConfigs(configs);
    } catch {
      // handled by empty state
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSave = async () => {
    if (!configuring || !clientId || !clientSecret) return;
    setSaving(true);
    try {
      await setOAuthConfig(configuring, clientId, clientSecret);
      toast.success(t('integrations.saveSuccess'));
      setConfiguring(null);
      setClientId('');
      setClientSecret('');
      loadData();
    } catch {
      toast.error(t('integrations.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (provider: CloudProvider) => {
    const confirmed = await confirm(
      t('integrations.deleteConfirm', { provider: PROVIDER_LABELS[provider] }),
      { title: t('integrations.delete'), confirmLabel: t('integrations.delete'), variant: 'danger' }
    );
    if (!confirmed) return;

    try {
      await deleteOAuthConfig(provider);
      toast.success(t('integrations.deleteSuccess'));
      loadData();
    } catch {
      toast.error(t('integrations.deleteFailed'));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {dialog}

      {/* Header */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-1 flex items-center">
          <Cloud className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('integrations.title')}
        </h3>
        <p className="text-sm text-slate-400">{t('integrations.description')}</p>
      </div>

      {/* Provider cards */}
      <div className="space-y-4">
        {PROVIDERS.map((p) => {
          const info = providerStatus?.providers[p.id];
          const isConfigured = info?.configured ?? false;
          const isOAuth = info?.auth_type === 'oauth';
          const isExpanded = configuring === p.id;

          return (
            <div
              key={p.id}
              className="rounded-2xl border border-slate-800/60 bg-slate-900/55 backdrop-blur-xl shadow-[0_20px_60px_rgba(2,6,23,0.55)] p-5"
            >
              <div className="flex items-center gap-4">
                {/* Provider icon */}
                <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${p.gradient} text-sm font-bold text-white`}>
                  {p.icon}
                </div>

                {/* Provider info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-200">{PROVIDER_LABELS[p.id]}</span>
                    {/* Status badge */}
                    {isOAuth && (
                      isConfigured ? (
                        <span className="flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">
                          <CheckCircle2 className="h-3 w-3" />
                          {t('integrations.configured')}
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 rounded-full border border-slate-600/30 bg-slate-600/10 px-2 py-0.5 text-xs font-medium text-slate-500">
                          <XCircle className="h-3 w-3" />
                          {t('integrations.notConfigured')}
                        </span>
                      )
                    )}
                  </div>

                  {/* Capability badges */}
                  <div className="mt-1 flex items-center gap-2">
                    {p.capabilities.includes('import') && (
                      <span className="rounded-md bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 text-xs text-sky-400">
                        {t('integrations.cloudImport')}
                      </span>
                    )}
                    {p.capabilities.includes('export') && (
                      <span className="rounded-md bg-violet-500/10 border border-violet-500/20 px-2 py-0.5 text-xs text-violet-400">
                        {t('integrations.cloudExport')}
                      </span>
                    )}
                    {p.id === 'icloud' && (
                      <span className="flex items-center gap-1 text-xs text-slate-500">
                        <Info className="h-3 w-3" />
                        {t('integrations.importOnly')}
                      </span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                {isOAuth && (
                  <div className="flex items-center gap-2">
                    {isConfigured ? (
                      <button
                        onClick={() => handleDelete(p.id)}
                        className="flex items-center gap-1.5 rounded-lg border border-slate-700/50 px-3 py-1.5 text-xs text-slate-400 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-400"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        {t('integrations.delete')}
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setConfiguring(isExpanded ? null : p.id);
                          setClientId('');
                          setClientSecret('');
                        }}
                        className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
                      >
                        <KeyRound className="h-3.5 w-3.5" />
                        {t('integrations.configure')}
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Inline config form */}
              {isExpanded && isOAuth && (
                <div className="mt-4 space-y-3 border-t border-slate-700/40 pt-4">
                  {PROVIDER_HELP_KEYS[p.id] && (
                    <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 px-3 py-2">
                      <p className="text-xs text-sky-400">
                        <ExternalLink className="mr-1 inline h-3 w-3" />
                        {t(`integrations.${PROVIDER_HELP_KEYS[p.id]}`)}
                      </p>
                    </div>
                  )}
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-400">
                      {t('integrations.clientId')}
                    </label>
                    <input
                      type="text"
                      value={clientId}
                      onChange={(e) => setClientId(e.target.value)}
                      placeholder={t('integrations.clientIdPlaceholder')}
                      className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-sky-500/50"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-400">
                      {t('integrations.clientSecret')}
                    </label>
                    <input
                      type="password"
                      value={clientSecret}
                      onChange={(e) => setClientSecret(e.target.value)}
                      placeholder={t('integrations.clientSecretPlaceholder')}
                      className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-sky-500/50"
                    />
                  </div>
                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => setConfiguring(null)}
                      className="rounded-lg border border-slate-700/50 px-4 py-2 text-sm text-slate-400 hover:bg-slate-800"
                    >
                      {t('integrations.cancel')}
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={saving || !clientId || !clientSecret}
                      className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                    >
                      {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                      {t('integrations.save')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Admin overview */}
      {isAdmin && (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <h3 className="text-base sm:text-lg font-semibold mb-1 flex items-center">
            <Users className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
            {t('integrations.adminOverview')}
          </h3>
          <p className="text-sm text-slate-400 mb-4">{t('integrations.adminOverviewDescription')}</p>

          {adminConfigs.length === 0 ? (
            <p className="text-sm text-slate-500 py-4 text-center">{t('integrations.noConfigs')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/40 text-left text-xs font-medium uppercase tracking-wider text-slate-500">
                    <th className="pb-2 pr-4">{t('integrations.user')}</th>
                    <th className="pb-2 pr-4">{t('integrations.provider')}</th>
                    <th className="pb-2 pr-4">{t('integrations.clientId')}</th>
                    <th className="pb-2">{t('integrations.lastUpdated')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/30">
                  {adminConfigs.map((c, i) => (
                    <tr key={`${c.user_id}-${c.provider}-${i}`} className="text-slate-300">
                      <td className="py-2.5 pr-4 font-medium">{c.username}</td>
                      <td className="py-2.5 pr-4">{PROVIDER_LABELS[c.provider] ?? c.provider}</td>
                      <td className="py-2.5 pr-4 font-mono text-xs text-slate-500">{c.client_id_hint ?? '—'}</td>
                      <td className="py-2.5 text-slate-500">
                        {c.updated_at ? new Date(c.updated_at).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/settings/IntegrationsTab.tsx
git commit -m "feat(settings): add IntegrationsTab component"
```

---

### Task 8: Frontend — Wire up IntegrationsTab in SettingsPage

**Files:**
- Modify: `client/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add import**

After the existing `StorageTab` import (line 12), add:

```typescript
import IntegrationsTab from '../components/settings/IntegrationsTab';
```

- [ ] **Step 2: Add `Plug` to lucide-react imports**

In line 5, add `Plug` to the icon imports:

```typescript
import { User, Lock, Clock, Download, Globe, KeyRound, GitBranch, Bell, HardDrive, Plug } from 'lucide-react';
```

- [ ] **Step 3: Add `'integrations'` to the tab type and valid tabs**

Line 30 — change the `SettingsTab` type:

```typescript
type SettingsTab = 'profile' | 'security' | 'storage' | 'language' | 'api-keys' | 'vcl' | 'notifications' | 'integrations';
```

Line 31 — add to `validTabs` array:

```typescript
const validTabs: SettingsTab[] = ['profile', 'security', 'storage', 'language', 'api-keys', 'vcl', 'notifications', 'integrations'];
```

- [ ] **Step 4: Add tab button**

In the tabs array (lines 145-152), add the integrations tab. Place it after notifications (line 151), before the admin-only api-keys spread:

```typescript
{ id: 'notifications' as const, label: t('tabs.notifications'), icon: Bell },
{ id: 'integrations' as const, label: t('tabs.integrations'), icon: Plug },
...(profile?.role === 'admin' ? [{ id: 'api-keys' as const, label: t('tabs.apiKeys'), icon: KeyRound }] : []),
```

- [ ] **Step 5: Add tab content rendering**

After the notifications tab content block (after line 354, before the closing `</div>`), add:

```tsx
{activeTab === 'integrations' && (
  <IntegrationsTab isAdmin={profile?.role === 'admin'} />
)}
```

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/SettingsPage.tsx
git commit -m "feat(settings): wire up Integrations tab in SettingsPage"
```

---

### Task 9: Frontend — Simplify CloudConnectWizard

**Files:**
- Modify: `client/src/components/cloud/CloudConnectWizard.tsx`

- [ ] **Step 1: Remove configure-related imports and constants**

Remove `Settings` and `ExternalLink` from the lucide imports (line 2). The updated import:

```typescript
import { X, ArrowRight, Loader2, KeyRound, Info } from 'lucide-react';
```

Remove `setOAuthConfig` from the API imports (line 8). The updated import:

```typescript
import {
  getOAuthUrl,
  getProviders,
  connectICloud,
  submitICloud2FA,
  createDevConnection,
  extractErrorMessage,
  type CloudProvider,
  type CloudConnection,
  type ProvidersStatus,
  PROVIDER_LABELS,
} from '../../api/cloud-import';
```

Remove the `PROVIDER_HELP` constant (lines 24-33) entirely.

- [ ] **Step 2: Remove configure-related state**

Remove from the component state (lines 46-48):

```typescript
const [configProvider, setConfigProvider] = useState<CloudProvider | null>(null);
const [clientId, setClientId] = useState('');
const [clientSecret, setClientSecret] = useState('');
```

Change the `step` state type (line 41) — remove `'configure'`:

```typescript
const [step, setStep] = useState<'provider' | 'icloud-login' | 'icloud-2fa'>('provider');
```

- [ ] **Step 3: Remove `handleSaveConfig` function**

Delete the `handleSaveConfig` function (lines 113-127) entirely.

- [ ] **Step 4: Update `handleSelectProvider` for unconfigured OAuth**

Replace the block at lines 88-95 (the section that enters the configure step for unconfigured providers):

Old:
```typescript
// Unconfigured OAuth provider — user can configure their own credentials
if (info && !info.configured && info.auth_type === 'oauth') {
  setConfigProvider(provider);
  setClientId('');
  setClientSecret('');
  setStep('configure');
  return;
}
```

New:
```typescript
// Unconfigured OAuth provider — redirect to settings
if (info && !info.configured && info.auth_type === 'oauth') {
  toast.error('Bitte zuerst in Settings > Integrations konfigurieren');
  window.location.href = '/settings?tab=integrations';
  return;
}
```

- [ ] **Step 5: Remove the configure step UI**

Delete the entire `{/* Step: Configure OAuth credentials */}` block (lines 250-300 area — the `step === 'configure'` section) from the JSX.

- [ ] **Step 6: Remove the provider selection hint for unconfigured providers**

In the provider selection step, remove the `Settings` icon references. Update the provider button to no longer show "Click to configure" — instead show a hint to go to Settings. Replace the unconfigured OAuth conditional in the provider button (lines 211-227):

Old:
```tsx
{!isDevMode && !isConfigured && isOAuth ? (
  <p className="flex items-center gap-1 text-xs text-sky-400/80">
    <Settings className="h-3 w-3" />
    Click to configure
  </p>
) : (
  <p className="text-xs text-slate-500">
    {isDevMode ? 'Mock connection' : `Connect via ${authHint}`}
  </p>
)}
```

New:
```tsx
{!isDevMode && !isConfigured && isOAuth ? (
  <p className="flex items-center gap-1 text-xs text-amber-400/80">
    <Info className="h-3 w-3" />
    Configure in Settings
  </p>
) : (
  <p className="text-xs text-slate-500">
    {isDevMode ? 'Mock connection' : `Connect via ${authHint}`}
  </p>
)}
```

Also update the trailing icon (lines 222-226):

Old:
```tsx
{!isDevMode && !isConfigured && isOAuth ? (
  <Settings className="h-4 w-4 text-sky-500/60" />
) : (
  <ArrowRight className="h-4 w-4 text-slate-600" />
)}
```

New:
```tsx
<ArrowRight className="h-4 w-4 text-slate-600" />
```

- [ ] **Step 7: Remove the unconfigured providers hint box**

Delete the hint box at lines 232-239 (the `{/* Hint for unconfigured providers */}` block) that says "Enter your own OAuth credentials...".

- [ ] **Step 8: Commit**

```bash
git add client/src/components/cloud/CloudConnectWizard.tsx
git commit -m "refactor(cloud): remove inline OAuth config from CloudConnectWizard

Unconfigured providers now redirect to Settings > Integrations."
```

---

### Task 10: Verify — Manual smoke test

- [ ] **Step 1: Run backend tests**

```bash
cd backend && python -m pytest tests/test_cloud_oauth_admin.py -v
```

Expected: All tests pass.

- [ ] **Step 2: Start dev server and verify**

```bash
python start_dev.py
```

1. Open `http://localhost:5173/settings?tab=integrations`
2. Verify: Three provider cards visible (Google Drive, OneDrive, iCloud)
3. Verify: Google Drive and OneDrive show "Not configured" with "Configure" button
4. Verify: iCloud shows "Import only" hint, no configure button
5. Click "Configure" on Google Drive — verify inline form appears
6. Navigate to `/cloud-import`, click "Add Connection", click Google Drive — verify redirect to Settings > Integrations
7. If logged in as admin: verify admin overview table appears at bottom

- [ ] **Step 3: Final commit (if any fixups needed)**

```bash
git add -A && git commit -m "fix: integrations tab polish"
```
