/**
 * Plugin Documentation Component
 *
 * Displays documentation about the plugin system, permissions, hooks, and risks.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  FileText,
  Shield,
  Zap,
  Folder,
  Users,
  Database,
  Network,
  Bell,
  Server,
  HardDrive,
  Activity,
  Smartphone,
  Key,
  Info,
} from 'lucide-react';
import type { PermissionInfo } from '../../api/plugins';
import { useFormattedVersion } from '../../contexts/VersionContext';

interface PluginDocumentationProps {
  permissions: PermissionInfo[];
}

// Hook category keys for iteration
const HOOK_CATEGORY_KEYS = ['file', 'user', 'backup', 'share', 'system', 'raid', 'smart', 'device', 'vpn'] as const;

// Hook names organized by category key
const HOOKS_BY_CATEGORY_KEY: Record<string, string[]> = {
  file: ['on_file_uploaded', 'on_file_deleted', 'on_file_moved', 'on_file_downloaded'],
  user: ['on_user_login', 'on_user_logout', 'on_user_created', 'on_user_deleted'],
  backup: ['on_backup_started', 'on_backup_completed'],
  share: ['on_share_created', 'on_share_accessed'],
  system: ['on_system_startup', 'on_system_shutdown', 'on_storage_threshold'],
  raid: ['on_raid_degraded', 'on_raid_rebuild_started', 'on_raid_rebuild_completed'],
  smart: ['on_disk_health_warning'],
  device: ['on_device_registered', 'on_device_removed'],
  vpn: ['on_vpn_client_created', 'on_vpn_client_revoked'],
};

// Permission category keys and their permissions
const PERMISSION_CATEGORY_KEYS = ['file', 'system', 'network', 'database', 'user', 'events'] as const;

const PERMISSION_CATEGORY_DATA: Record<string, { icon: React.ElementType; permissions: string[] }> = {
  file: {
    icon: FileText,
    permissions: ['file:read', 'file:write', 'file:delete'],
  },
  system: {
    icon: Server,
    permissions: ['system:info', 'system:execute'],
  },
  network: {
    icon: Network,
    permissions: ['network:outbound'],
  },
  database: {
    icon: Database,
    permissions: ['db:read', 'db:write'],
  },
  user: {
    icon: Users,
    permissions: ['user:read', 'user:write'],
  },
  events: {
    icon: Zap,
    permissions: ['notification:send', 'task:background', 'event:subscribe', 'event:emit'],
  },
};

// Icons for hook categories
const HOOK_CATEGORY_ICONS: Record<string, React.ElementType> = {
  file: FileText,
  user: Users,
  backup: HardDrive,
  share: Folder,
  system: Server,
  raid: Activity,
  smart: HardDrive,
  device: Smartphone,
  vpn: Key,
};

export default function PluginDocumentation({ permissions }: PluginDocumentationProps) {
  const { t } = useTranslation('plugins');
  // Create a lookup map for permission details
  const permissionMap = new Map(permissions.map((p) => [p.value, p]));
  const formattedVersion = useFormattedVersion('BaluHost');

  // Build hooks data with translations
  const hooksByCategory = useMemo(() => {
    return HOOK_CATEGORY_KEYS.map((key) => ({
      key,
      label: t(`hookCategories.${key}`),
      hooks: HOOKS_BY_CATEGORY_KEY[key].map((hookName) => ({
        name: hookName,
        description: t(`hooks.${hookName}`),
      })),
    }));
  }, [t]);

  // Build permission categories with translations
  const permissionCategories = useMemo(() => {
    return PERMISSION_CATEGORY_KEYS.map((key) => ({
      key,
      label: t(`categories.${key}`),
      icon: PERMISSION_CATEGORY_DATA[key].icon,
      permissions: PERMISSION_CATEGORY_DATA[key].permissions,
    }));
  }, [t]);

  // Total hooks count
  const totalHooks = useMemo(() => {
    return hooksByCategory.reduce((sum, cat) => sum + cat.hooks.length, 0);
  }, [hooksByCategory]);

  return (
    <div className="space-y-6">
      {/* Risk Warning Banner */}
      <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-amber-200">{t('docs.securityWarning')}</h3>
            <p className="mt-1 text-sm text-amber-200/80">
              {t('docs.securityWarningDescription')}
            </p>
            <div className="mt-3">
              <p className="text-xs font-medium text-amber-300">
                {t('docs.dangerousPermissions')}:
              </p>
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

      {/* System Overview */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Info className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('docs.systemOverview')}</h2>
        </div>
        <div className="space-y-4 text-sm text-slate-300">
          <div>
            <h3 className="font-medium text-white mb-2">{t('docs.installation')}</h3>
            <p className="text-slate-400">
              {t('docs.installationDesc')
                .split('{{path}}')
                .map((part, i, arr) => (
                  <span key={i}>
                    {part.split('{{manifest}}').map((subPart, j, subArr) => (
                      <span key={j}>
                        {subPart}
                        {j < subArr.length - 1 && (
                          <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sky-400 text-xs">
                            plugin.json
                          </code>
                        )}
                      </span>
                    ))}
                    {i < arr.length - 1 && (
                      <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sky-400 text-xs">
                        backend/app/plugins/installed/
                      </code>
                    )}
                  </span>
                ))}
            </p>
          </div>
          <div>
            <h3 className="font-medium text-white mb-2">{t('docs.lifecycle')}</h3>
            <ol className="list-decimal list-inside text-slate-400 space-y-1">
              <li><span className="text-slate-300">{t('docs.discovery')}</span> - {t('docs.discoveryDesc')}</li>
              <li><span className="text-slate-300">{t('docs.registration')}</span> - {t('docs.registrationDesc')}</li>
              <li><span className="text-slate-300">{t('docs.permissionCheck')}</span> - {t('docs.permissionCheckDesc')}</li>
              <li><span className="text-slate-300">{t('docs.activation')}</span> - {t('docs.activationDesc')}</li>
            </ol>
          </div>
          <div>
            <h3 className="font-medium text-white mb-2">{t('docs.pluginStructure')}</h3>
            <pre className="p-3 rounded-lg bg-slate-800/50 text-xs text-slate-400 overflow-x-auto">
{`my_plugin/
├── plugin.json      # ${t('docs.pluginStructureManifest')}
├── __init__.py      # ${t('docs.pluginStructureEntry')}
├── routes.py        # ${t('docs.pluginStructureRoutes')}
└── ui/
    └── bundle.js    # ${t('docs.pluginStructureUI')}`}
            </pre>
          </div>
        </div>
      </div>

      {/* Permissions Section */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('docs.permissions')}</h2>
          <span className="text-xs text-slate-500">({permissions.length} {t('docs.available')})</span>
        </div>
        <p className="text-sm text-slate-400 mb-4">
          {t('docs.permissionsDescription')}
        </p>
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
                        {perm.dangerous && (
                          <AlertTriangle className="h-3 w-3 text-amber-400" />
                        )}
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        {t(`permissionDescriptions.${perm.value}`, { defaultValue: perm.description })}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>

      {/* Hooks Reference */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('docs.eventHooks')}</h2>
          <span className="text-xs text-slate-500">
            ({totalHooks} {t('docs.hooks')})
          </span>
        </div>
        <p className="text-sm text-slate-400 mb-4">
          {t('docs.eventHooksDescription')}{' '}
          <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sky-400 text-xs">event:subscribe</code>{' '}
          {t('docs.required')}.
        </p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {hooksByCategory.map((category) => {
            const CategoryIcon = HOOK_CATEGORY_ICONS[category.key] || Bell;
            return (
              <div key={category.key} className="rounded-lg border border-slate-700 bg-slate-800/30 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <CategoryIcon className="h-4 w-4 text-slate-400" />
                  <h3 className="text-sm font-medium text-white">{category.label}</h3>
                  <span className="text-xs text-slate-500">({category.hooks.length})</span>
                </div>
                <ul className="space-y-2">
                  {category.hooks.map((hook) => (
                    <li key={hook.name} className="text-xs">
                      <code className="text-sky-400">{hook.name}</code>
                      <p className="text-slate-500 mt-0.5">{hook.description}</p>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>

      {/* Version Info */}
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
