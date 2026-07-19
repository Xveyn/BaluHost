import type { TFunction } from 'i18next';
import { Plug, CloudDownload, Shield, Zap } from 'lucide-react';

export interface LayoutNavItem {
  path: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
  isPlugin?: boolean;
}

// Pi mode: only show Dashboard + System
export const PI_NAV_PATHS: ReadonlySet<string> = new Set(['/', '/system']);

export const navIcon = {
  dashboard: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <rect x="3" y="3" width="8" height="8" rx="1.6" stroke="currentColor" />
      <rect x="13" y="3" width="8" height="5" rx="1.6" stroke="currentColor" />
      <rect x="13" y="10" width="8" height="11" rx="1.6" stroke="currentColor" />
      <rect x="3" y="13" width="8" height="8" rx="1.6" stroke="currentColor" />
    </svg>
  ),
  files: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M4 7.5A2.5 2.5 0 0 1 6.5 5H12l2 2h3.5A2.5 2.5 0 0 1 20 9.5V18a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 18V7.5Z" />
      <path stroke="currentColor" strokeLinecap="round" d="M8 14h8" />
      <path stroke="currentColor" strokeLinecap="round" d="M8 11h4" />
    </svg>
  ),
  system: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M4 12h3l2 7 3-14 2 7h6" />
    </svg>
  ),
  logging: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z" />
      <path stroke="currentColor" strokeLinecap="round" d="M7 9h10" />
      <path stroke="currentColor" strokeLinecap="round" d="M7 13h10" />
      <path stroke="currentColor" strokeLinecap="round" d="M7 17h6" />
    </svg>
  ),
  users: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <circle cx="12" cy="7.5" r="3.5" stroke="currentColor" />
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M5.5 18.5A6.5 6.5 0 0 1 12 14a6.5 6.5 0 0 1 6.5 4.5" />
    </svg>
  ),
  raid: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <circle cx="12" cy="12" r="8" stroke="currentColor" />
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 4v4" />
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 16v4" />
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M4 12h4" />
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M16 12h4" />
      <circle cx="12" cy="12" r="2.5" stroke="currentColor" />
    </svg>
  ),
  docs: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M7 8h10M7 12h10M7 16h6" />
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z" />
      <path stroke="currentColor" strokeLinecap="round" d="M9 4v16" />
    </svg>
  ),
  shares: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <circle cx="18" cy="5" r="3" stroke="currentColor" />
      <circle cx="6" cy="12" r="3" stroke="currentColor" />
      <circle cx="18" cy="19" r="3" stroke="currentColor" />
      <path stroke="currentColor" strokeLinecap="round" d="M8.7 10.7L15.3 6.3M8.7 13.3L15.3 17.7" />
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <circle cx="12" cy="12" r="3" stroke="currentColor" />
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 8.5v-2a1.5 1.5 0 0 1 1.5-1.5h0a1.5 1.5 0 0 1 1.5 1.5v2m-3 7v2a1.5 1.5 0 0 0 1.5 1.5h0a1.5 1.5 0 0 0 1.5-1.5v-2m-7-3.5h-2a1.5 1.5 0 0 1-1.5-1.5v0a1.5 1.5 0 0 1 1.5-1.5h2m7 3h2a1.5 1.5 0 0 0 1.5-1.5v0a1.5 1.5 0 0 0-1.5-1.5h-2" />
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M16.2 7.8l1.4-1.4a1.5 1.5 0 0 1 2.1 0v0a1.5 1.5 0 0 1 0 2.1l-1.4 1.4m-10.6 0L6.3 8.5a1.5 1.5 0 0 1 0-2.1v0a1.5 1.5 0 0 1 2.1 0l1.4 1.4m0 8.4l-1.4 1.4a1.5 1.5 0 0 1-2.1 0v0a1.5 1.5 0 0 1 0-2.1l1.4-1.4m8.4 0l1.4 1.4a1.5 1.5 0 0 0 2.1 0v0a1.5 1.5 0 0 0 0-2.1l-1.4-1.4" />
    </svg>
  ),
  sync: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M21 3v5h-5" />
      <circle cx="12" cy="12" r="2" fill="currentColor" />
    </svg>
  ),
  mobile: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <rect x="7" y="3" width="10" height="18" rx="2" stroke="currentColor" />
      <path stroke="currentColor" strokeLinecap="round" d="M12 18h0" />
    </svg>
  ),
  scheduler: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2" />
      <circle cx="12" cy="12" r="9" stroke="currentColor" />
    </svg>
  ),
  database: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <rect x="3" y="4" width="18" height="6" rx="1.5" stroke="currentColor" />
      <rect x="3" y="14" width="18" height="6" rx="1.5" stroke="currentColor" />
      <path stroke="currentColor" strokeLinecap="round" d="M7 10v4" />
    </svg>
  ),
  updates: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 3v12m0 0l4-4m-4 4l-4-4" />
      <path stroke="currentColor" strokeLinecap="round" d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
    </svg>
  ),
  systemControl: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065Z" />
      <circle cx="12" cy="12" r="3" stroke="currentColor" />
    </svg>
  ),
  devices: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <rect x="5" y="2" width="14" height="20" rx="2" stroke="currentColor" />
      <path stroke="currentColor" strokeLinecap="round" d="M12 18h0" />
      <rect x="9" y="6" width="6" height="8" rx="1" stroke="currentColor" />
    </svg>
  ),
} as const;

export const pluginNavIcon = <Plug className="h-5 w-5" />;

export function buildNavItems(t: TFunction): LayoutNavItem[] {
  return [
    // Main items (everyone)
    {
      path: '/',
      label: t('navigation.dashboard'),
      description: t('navigation.dashboardDesc'),
      icon: navIcon.dashboard,
    },
    {
      path: '/files',
      label: t('navigation.files'),
      description: t('navigation.filesDesc'),
      icon: navIcon.files,
    },
    {
      path: '/shares',
      label: t('navigation.shares'),
      description: t('navigation.sharesDesc'),
      icon: navIcon.shares,
    },
    {
      path: '/system',
      label: t('navigation.system'),
      description: t('navigation.systemDesc'),
      icon: navIcon.system,
    },
    {
      path: '/devices',
      label: t('navigation.devices'),
      description: t('navigation.devicesDesc'),
      icon: navIcon.devices,
    },
    {
      path: '/smart-devices',
      label: t('navigation.smartDevices', 'Smart Devices'),
      description: t('navigation.smartDevicesDesc', 'IoT device control'),
      icon: <Zap className="h-5 w-5" />,
    },
    {
      path: '/settings',
      label: t('navigation.settings'),
      description: t('navigation.settingsDesc'),
      icon: navIcon.settings,
    },
    {
      path: '/manual',
      label: t('navigation.userManual'),
      description: t('navigation.userManualDesc'),
      icon: navIcon.docs,
    },
    {
      path: '/cloud-import',
      label: t('navigation.cloudImport'),
      description: t('navigation.cloudImportDesc'),
      icon: <CloudDownload className="h-5 w-5" />,
    },
    // Admin items
    {
      path: '/admin/system-control',
      label: t('navigation.systemControl'),
      description: t('navigation.systemControlDesc'),
      icon: navIcon.systemControl,
      adminOnly: true,
    },
    {
      path: '/schedulers',
      label: t('navigation.scheduler'),
      description: t('navigation.schedulerDesc'),
      icon: navIcon.scheduler,
      adminOnly: true,
    },
    {
      path: '/admin-db',
      label: t('navigation.database'),
      description: t('navigation.databaseDesc'),
      icon: navIcon.database,
      adminOnly: true,
    },
    {
      path: '/users',
      label: t('navigation.users'),
      description: t('navigation.usersDesc'),
      icon: navIcon.users,
      adminOnly: true,
    },
    {
      path: '/pihole',
      label: 'Pi-hole DNS',
      description: 'DNS Filtering',
      icon: <Shield className="h-5 w-5" />,
      adminOnly: true,
    },
    {
      path: '/plugins',
      label: t('navigation.plugins'),
      description: t('navigation.pluginsDesc'),
      icon: <Plug className="h-5 w-5" />,
      adminOnly: true,
    },
    {
      path: '/updates',
      label: t('navigation.updates'),
      description: t('navigation.updatesDesc'),
      icon: navIcon.updates,
      adminOnly: true,
    },
  ];
}
