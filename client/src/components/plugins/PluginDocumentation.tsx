/**
 * Plugin Documentation Component
 *
 * Operator-focused reference for the plugin system: the two trust tiers
 * (bundled in-process/trusted vs external sandboxed), the external
 * capability-scope model (rendered from the live catalog), and a condensed
 * bundled-plugin reference.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  FileText,
  Shield,
  ShieldCheck,
  Boxes,
  Zap,
  Users,
  Database,
  Network,
  Server,
  Plug,
  Info,
  Store,
} from 'lucide-react';
import type { PermissionInfo, ScopeInfo } from '../../api/plugins';
import { useFormattedVersion } from '../../contexts/VersionContext';

interface PluginDocumentationProps {
  permissions: PermissionInfo[];
  scopeCatalog: ScopeInfo[];
}

// Permission category keys and their permissions (bundled plugins only).
const PERMISSION_CATEGORY_KEYS = ['file', 'system', 'network', 'database', 'user', 'device', 'events'] as const;

const PERMISSION_CATEGORY_DATA: Record<string, { icon: React.ElementType; permissions: string[] }> = {
  file: { icon: FileText, permissions: ['file:read', 'file:write', 'file:delete'] },
  system: { icon: Server, permissions: ['system:info', 'system:execute'] },
  network: { icon: Network, permissions: ['network:outbound'] },
  database: { icon: Database, permissions: ['db:read', 'db:write'] },
  user: { icon: Users, permissions: ['user:read', 'user:write'] },
  device: { icon: Plug, permissions: ['device:control'] },
  events: { icon: Zap, permissions: ['notification:send', 'task:background', 'event:subscribe', 'event:emit'] },
};

export default function PluginDocumentation({ permissions, scopeCatalog }: PluginDocumentationProps) {
  const { t } = useTranslation('plugins');
  const permissionMap = new Map(permissions.map((p) => [p.value, p]));
  const formattedVersion = useFormattedVersion('BaluHost');

  // Separator-safe scope-description lookup (scope keys contain ':' and '.').
  // `nsSeparator: false` is required in addition to `returnObjects: true`:
  // i18next re-parses each nested key against the namespace separator while
  // building the returned object, so a key like "read:system-info" still
  // collapses to just "system-info" (or the whole {label, description}
  // object to a string) unless nsSeparator is disabled for this call (#288).
  const scopeDescs = t('scopeDescriptions', { returnObjects: true, nsSeparator: false }) as Record<
    string,
    { label: string; description: string }
  >;

  // Separator-safe permission-description lookup (#288): permission keys
  // contain ':' (e.g. "file:read"), which i18next's nsSeparator otherwise
  // mis-parses as namespace.key, silently falling back to the EN API copy.
  // See the scopeDescs comment above for why nsSeparator: false is required
  // here too, not just returnObjects: true.
  const permissionDescs = t('permissionDescriptions', {
    returnObjects: true,
    nsSeparator: false,
  }) as Record<string, string>;

  const permissionCategories = useMemo(() => {
    return PERMISSION_CATEGORY_KEYS.map((key) => ({
      key,
      label: t(`categories.${key}`),
      icon: PERMISSION_CATEGORY_DATA[key].icon,
      permissions: PERMISSION_CATEGORY_DATA[key].permissions,
    }));
  }, [t]);

  return (
    <div className="space-y-6">
      {/* 1. Security banner (reframed, two-tier) */}
      <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-amber-200">{t('docs.securityWarning')}</h3>
            <p className="mt-1 text-sm text-amber-200/80">{t('docs.securityWarningDescription')}</p>
            <div className="mt-3">
              <p className="text-xs font-medium text-amber-300">{t('docs.dangerousPermissions')}:</p>
              <ul className="mt-1 text-xs text-amber-200/70 space-y-1">
                <li>• <code className="text-amber-300">file:write</code> - {t('docs.permissionDescFileWrite')}</li>
                <li>• <code className="text-amber-300">file:delete</code> - {t('docs.permissionDescFileDelete')}</li>
                <li>• <code className="text-amber-300">system:execute</code> - {t('docs.permissionDescSystemExecute')}</li>
                <li>• <code className="text-amber-300">db:write</code> - {t('docs.permissionDescDbWrite')}</li>
                <li>• <code className="text-amber-300">user:write</code> - {t('docs.permissionDescUserWrite')}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Trust tiers (centerpiece) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('tiers.title')}</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-4">
            <div className="flex items-center gap-2 mb-2">
              <ShieldCheck className="h-5 w-5 text-emerald-400" />
              <h3 className="text-sm font-medium text-white">{t('tiers.bundled.label')}</h3>
            </div>
            <p className="text-sm text-slate-400">{t('tiers.bundled.description')}</p>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-4">
            <div className="flex items-center gap-2 mb-2">
              <Boxes className="h-5 w-5 text-sky-400" />
              <h3 className="text-sm font-medium text-white">{t('tiers.external.label')}</h3>
            </div>
            <p className="text-sm text-slate-400">{t('tiers.external.description')}</p>
          </div>
        </div>
      </div>

      {/* 3. Capability scopes (external, from live catalog) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Boxes className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('tiers.scopesTitle')}</h2>
        </div>
        <p className="text-sm text-slate-400 mb-4">{t('tiers.scopesIntro')}</p>
        {scopeCatalog.length === 0 ? (
          <p className="text-sm text-slate-500">{t('tiers.scopesUnavailable')}</p>
        ) : (
          <div className="space-y-4">
            {(['frontend', 'backend'] as const).map((tier) => {
              const scopes = scopeCatalog.filter((s) => s.tier === tier);
              if (scopes.length === 0) return null;
              return (
                <div key={tier} className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {t(`scopeTiers.${tier}`)}
                  </div>
                  <ul className="space-y-2">
                    {scopes.map((scope) => {
                      const meta = scopeDescs?.[scope.key];
                      return (
                        <li key={scope.key} className="rounded-lg border border-slate-700 bg-slate-800/30 p-3">
                          <div className="flex items-center gap-2">
                            <code className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">{scope.key}</code>
                            <span className="text-sm font-medium text-white">{meta?.label ?? scope.key}</span>
                            {scope.dangerous && <AlertTriangle className="h-3 w-3 text-amber-400" />}
                          </div>
                          {meta?.description && <p className="text-xs text-slate-500 mt-1">{meta.description}</p>}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 4. Installing & enabling (reframed) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Info className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('tiers.installTitle')}</h2>
        </div>
        <div className="space-y-4 text-sm text-slate-300">
          <div>
            <h3 className="font-medium text-white mb-1">{t('tiers.external.label')}</h3>
            <p className="text-slate-400">{t('tiers.installExternal')}</p>
          </div>
          <div>
            <h3 className="font-medium text-white mb-1">{t('tiers.bundled.label')}</h3>
            <p className="text-slate-400">{t('tiers.installBundled')}</p>
          </div>
          <div className="flex items-start gap-2 rounded-lg border border-sky-500/30 bg-sky-500/5 p-3">
            <Store className="h-4 w-4 text-sky-400 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-sky-200/90">{t('docs.marketplaceHint')}</p>
          </div>
        </div>
      </div>

      {/* 5a. Bundled reference — permission categories (condensed) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('docs.permissions')}</h2>
          <span className="text-xs text-slate-500">({permissions.length} {t('docs.available')})</span>
        </div>
        <p className="text-sm text-slate-400 mb-4">{t('docs.permissionsDescription')}</p>
        <div className="grid gap-4 md:grid-cols-2">
          {permissionCategories.map((category) => {
            const CategoryIcon = category.icon;
            const categoryPerms = category.permissions
              .map((p) => permissionMap.get(p))
              .filter((p): p is PermissionInfo => p !== undefined);

            if (categoryPerms.length === 0) return null;

            return (
              <div key={category.key} className="rounded-lg border border-slate-700 bg-slate-800/30 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <CategoryIcon className="h-4 w-4 text-slate-400" />
                  <h3 className="text-sm font-medium text-white">{category.label}</h3>
                </div>
                <ul className="space-y-2">
                  {categoryPerms.map((perm) => (
                    <li key={perm.value} className="text-sm">
                      <div className="flex items-center gap-2">
                        <code
                          className={`text-xs px-1.5 py-0.5 rounded ${
                            perm.dangerous
                              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                              : 'bg-slate-700 text-slate-300'
                          }`}
                        >
                          {perm.value}
                        </code>
                        {perm.dangerous && <AlertTriangle className="h-3 w-3 text-amber-400" />}
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        {permissionDescs?.[perm.value] ?? perm.description}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>

      {/* 5b. Bundled reference — event hooks (summary + GitHub link) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-2">
          <Zap className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('docs.eventHooks')}</h2>
        </div>
        <p className="text-sm text-slate-400">
          {t('docs.eventHooksDescription')}{' '}
          <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sky-400 text-xs">event:subscribe</code>{' '}
          {t('docs.required')}.{' '}
          <a
            href="https://github.com/Xveyn/BaluHost"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sky-400 hover:underline"
          >
            {t('docs.documentationOnGitHub')}
          </a>
        </p>
      </div>

      {/* 6. Version footer (unchanged) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-4 text-slate-400">
            <span>{formattedVersion}</span>
            <span className="text-slate-600">|</span>
            <span>Plugin API v1.0</span>
          </div>
          <a
            href="https://github.com/Xveyn/BaluHost"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sky-400 hover:underline text-xs"
          >
            {t('docs.documentationOnGitHub')}
          </a>
        </div>
      </div>
    </div>
  );
}
