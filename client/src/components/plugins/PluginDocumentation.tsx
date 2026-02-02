/**
 * Plugin Documentation Component
 *
 * Displays documentation about the plugin system, permissions, hooks, and risks.
 */
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

// Hook definitions organized by category
const HOOKS_BY_CATEGORY = {
  'Datei-Events': [
    { name: 'on_file_uploaded', description: 'Wird ausgelöst wenn eine Datei hochgeladen wird' },
    { name: 'on_file_deleted', description: 'Wird ausgelöst wenn eine Datei gelöscht wird' },
    { name: 'on_file_moved', description: 'Wird ausgelöst wenn eine Datei verschoben/umbenannt wird' },
    { name: 'on_file_downloaded', description: 'Wird ausgelöst wenn eine Datei heruntergeladen wird' },
  ],
  'Benutzer-Events': [
    { name: 'on_user_login', description: 'Wird ausgelöst bei Benutzeranmeldung' },
    { name: 'on_user_logout', description: 'Wird ausgelöst bei Benutzerabmeldung' },
    { name: 'on_user_created', description: 'Wird ausgelöst wenn ein neuer Benutzer erstellt wird' },
    { name: 'on_user_deleted', description: 'Wird ausgelöst wenn ein Benutzer gelöscht wird' },
  ],
  'Backup-Events': [
    { name: 'on_backup_started', description: 'Wird ausgelöst wenn ein Backup startet' },
    { name: 'on_backup_completed', description: 'Wird ausgelöst wenn ein Backup abgeschlossen ist' },
  ],
  'Share-Events': [
    { name: 'on_share_created', description: 'Wird ausgelöst wenn ein Share erstellt wird' },
    { name: 'on_share_accessed', description: 'Wird ausgelöst wenn auf einen Share zugegriffen wird' },
  ],
  'System-Events': [
    { name: 'on_system_startup', description: 'Wird ausgelöst beim Systemstart' },
    { name: 'on_system_shutdown', description: 'Wird ausgelöst beim Herunterfahren' },
    { name: 'on_storage_threshold', description: 'Wird ausgelöst bei Speicherplatz-Warnung' },
  ],
  'RAID-Events': [
    { name: 'on_raid_degraded', description: 'Wird ausgelöst wenn ein RAID-Array degradiert' },
    { name: 'on_raid_rebuild_started', description: 'Wird ausgelöst wenn ein Rebuild startet' },
    { name: 'on_raid_rebuild_completed', description: 'Wird ausgelöst wenn ein Rebuild abgeschlossen ist' },
  ],
  'SMART-Events': [
    { name: 'on_disk_health_warning', description: 'Wird ausgelöst bei Disk-Health-Warnung' },
  ],
  'Device-Events': [
    { name: 'on_device_registered', description: 'Wird ausgelöst wenn ein Gerät registriert wird' },
    { name: 'on_device_removed', description: 'Wird ausgelöst wenn ein Gerät entfernt wird' },
  ],
  'VPN-Events': [
    { name: 'on_vpn_client_created', description: 'Wird ausgelöst wenn ein VPN-Client erstellt wird' },
    { name: 'on_vpn_client_revoked', description: 'Wird ausgelöst wenn ein VPN-Client widerrufen wird' },
  ],
};

// Permission categories for grouping
const PERMISSION_CATEGORIES: Record<string, { label: string; icon: React.ElementType; permissions: string[] }> = {
  file: {
    label: 'Datei',
    icon: FileText,
    permissions: ['file:read', 'file:write', 'file:delete'],
  },
  system: {
    label: 'System',
    icon: Server,
    permissions: ['system:info', 'system:execute'],
  },
  network: {
    label: 'Netzwerk',
    icon: Network,
    permissions: ['network:outbound'],
  },
  database: {
    label: 'Datenbank',
    icon: Database,
    permissions: ['db:read', 'db:write'],
  },
  user: {
    label: 'Benutzer',
    icon: Users,
    permissions: ['user:read', 'user:write'],
  },
  events: {
    label: 'Events & Tasks',
    icon: Zap,
    permissions: ['notification:send', 'task:background', 'event:subscribe', 'event:emit'],
  },
};

// Icons for hook categories
const HOOK_CATEGORY_ICONS: Record<string, React.ElementType> = {
  'Datei-Events': FileText,
  'Benutzer-Events': Users,
  'Backup-Events': HardDrive,
  'Share-Events': Folder,
  'System-Events': Server,
  'RAID-Events': Activity,
  'SMART-Events': HardDrive,
  'Device-Events': Smartphone,
  'VPN-Events': Key,
};

export default function PluginDocumentation({ permissions }: PluginDocumentationProps) {
  const { t } = useTranslation('plugins');
  // Create a lookup map for permission details
  const permissionMap = new Map(permissions.map((p) => [p.value, p]));
  const formattedVersion = useFormattedVersion('BaluHost');

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
                <li>• <code className="text-amber-300">file:write</code> - Dateien schreiben/ändern</li>
                <li>• <code className="text-amber-300">file:delete</code> - Dateien löschen</li>
                <li>• <code className="text-amber-300">system:execute</code> - System-Befehle ausführen</li>
                <li>• <code className="text-amber-300">db:write</code> - Datenbank ändern</li>
                <li>• <code className="text-amber-300">user:write</code> - Benutzerkonten ändern</li>
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
              Plugins werden als Verzeichnisse im Ordner{' '}
              <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sky-400 text-xs">
                backend/app/plugins/installed/
              </code>{' '}
              installiert. Jedes Plugin benötigt eine{' '}
              <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sky-400 text-xs">
                plugin.json
              </code>{' '}
              Manifest-Datei.
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
├── plugin.json      # Manifest (Name, Version, Permissions)
├── __init__.py      # Plugin-Einstiegspunkt
├── routes.py        # Optional: API-Routen
└── ui/
    └── bundle.js    # Optional: Frontend-Komponente`}
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
          {Object.entries(PERMISSION_CATEGORIES).map(([key, category]) => {
            const CategoryIcon = category.icon;
            const categoryPerms = category.permissions
              .map((p) => permissionMap.get(p))
              .filter((p): p is PermissionInfo => p !== undefined);

            if (categoryPerms.length === 0) return null;

            return (
              <div key={key} className="rounded-lg border border-slate-700 bg-slate-800/30 p-4">
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
                      <p className="text-xs text-slate-500 mt-1">{perm.description}</p>
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
            ({Object.values(HOOKS_BY_CATEGORY).flat().length} {t('docs.hooks')})
          </span>
        </div>
        <p className="text-sm text-slate-400 mb-4">
          {t('docs.eventHooksDescription')}{' '}
          <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sky-400 text-xs">event:subscribe</code>{' '}
          {t('docs.required')}.
        </p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Object.entries(HOOKS_BY_CATEGORY).map(([category, hooks]) => {
            const CategoryIcon = HOOK_CATEGORY_ICONS[category] || Bell;
            return (
              <div key={category} className="rounded-lg border border-slate-700 bg-slate-800/30 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <CategoryIcon className="h-4 w-4 text-slate-400" />
                  <h3 className="text-sm font-medium text-white">{category}</h3>
                  <span className="text-xs text-slate-500">({hooks.length})</span>
                </div>
                <ul className="space-y-2">
                  {hooks.map((hook) => (
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
