import { Link, useLocation } from 'react-router-dom';
import { type ReactNode, useState } from 'react';
import { useTranslation } from 'react-i18next';
import logoMark from '../assets/baluhost-logo.png';
import { localApi } from '../lib/localApi';
import { AdminBadge } from './ui/AdminBadge';
import { DeveloperBadge } from './ui/DeveloperBadge';
import { usePlugins } from '../contexts/PluginContext';
import { useFormattedVersion } from '../contexts/VersionContext';
import { Plug, CloudDownload } from 'lucide-react';
import NotificationCenter from './NotificationCenter';
import { UploadProgressBar } from './UploadProgressBar';

interface LayoutProps {
  children: ReactNode;
  user: {
    username: string;
    role: string;
  };
  onLogout: () => void;
}

interface NavItem {
  path: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
}

const navIcon = {
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
  )
} as const;

export default function Layout({ children, user, onLogout }: LayoutProps) {
  const location = useLocation();
  const { t } = useTranslation('common');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [shutdownPending, setShutdownPending] = useState(false);
  const [shutdownMessage, setShutdownMessage] = useState<string | null>(null);
  const { pluginNavItems } = usePlugins();
  const formattedVersion = useFormattedVersion('');

  // Icons for navigation items
  const schedulerIcon = (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2" />
      <circle cx="12" cy="12" r="9" stroke="currentColor" />
    </svg>
  );

  const databaseIcon = (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <rect x="3" y="4" width="18" height="6" rx="1.5" stroke="currentColor" />
      <rect x="3" y="14" width="18" height="6" rx="1.5" stroke="currentColor" />
      <path stroke="currentColor" strokeLinecap="round" d="M7 10v4" />
    </svg>
  );

  const updatesIcon = (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 3v12m0 0l4-4m-4 4l-4-4" />
      <path stroke="currentColor" strokeLinecap="round" d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
    </svg>
  );

  // System control icon for combined admin page
  const systemControlIcon = (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065Z" />
      <circle cx="12" cy="12" r="3" stroke="currentColor" />
    </svg>
  );

  // Devices icon for combined devices page
  const devicesIcon = (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <rect x="5" y="2" width="14" height="20" rx="2" stroke="currentColor" />
      <path stroke="currentColor" strokeLinecap="round" d="M12 18h0" />
      <rect x="9" y="6" width="6" height="8" rx="1" stroke="currentColor" />
    </svg>
  );

  // Flat navigation structure (no sections)
  const navItems: NavItem[] = [
    // Main items (everyone)
    {
      path: '/',
      label: t('navigation.dashboard'),
      description: t('navigation.dashboardDesc'),
      icon: navIcon.dashboard
    },
    {
      path: '/files',
      label: t('navigation.files'),
      description: t('navigation.filesDesc'),
      icon: navIcon.files
    },
    {
      path: '/shares',
      label: t('navigation.shares'),
      description: t('navigation.sharesDesc'),
      icon: navIcon.shares
    },
    {
      path: '/system',
      label: t('navigation.system'),
      description: t('navigation.systemDesc'),
      icon: navIcon.system
    },
    {
      path: '/devices',
      label: t('navigation.devices'),
      description: t('navigation.devicesDesc'),
      icon: devicesIcon
    },
    {
      path: '/settings',
      label: t('navigation.settings'),
      description: t('navigation.settingsDesc'),
      icon: navIcon.settings
    },
    {
      path: '/docs',
      label: t('navigation.apiCenter'),
      description: t('navigation.apiCenterDesc'),
      icon: navIcon.docs
    },
    {
      path: '/cloud-import',
      label: t('navigation.cloudImport'),
      description: t('navigation.cloudImportDesc'),
      icon: <CloudDownload className="h-5 w-5" />
    },
    // Admin items
    {
      path: '/admin/system-control',
      label: t('navigation.systemControl'),
      description: t('navigation.systemControlDesc'),
      icon: systemControlIcon,
      adminOnly: true
    },
    {
      path: '/schedulers',
      label: t('navigation.scheduler'),
      description: t('navigation.schedulerDesc'),
      icon: schedulerIcon,
      adminOnly: true
    },
    {
      path: '/admin-db',
      label: t('navigation.database'),
      description: t('navigation.databaseDesc'),
      icon: databaseIcon,
      adminOnly: true
    },
    {
      path: '/users',
      label: t('navigation.users'),
      description: t('navigation.usersDesc'),
      icon: navIcon.users,
      adminOnly: true
    },
    {
      path: '/plugins',
      label: t('navigation.plugins'),
      description: t('navigation.pluginsDesc'),
      icon: <Plug className="h-5 w-5" />,
      adminOnly: true
    },
    {
      path: '/updates',
      label: t('navigation.updates'),
      description: t('navigation.updatesDesc'),
      icon: updatesIcon,
      adminOnly: true
    }
  ];

  // Add plugin navigation items
  const pluginItems = pluginNavItems
    .filter((item) => !item.admin_only || user.role === 'admin')
    .map((item) => ({
      path: `/plugins/${item.path}`,
      label: item.label,
      description: 'Plugin',
      icon: <Plug className="h-5 w-5" />,
      adminOnly: item.admin_only
    }));

  // Filter nav items based on user role
  const filteredNavItems = navItems
    .filter(item => !item.adminOnly || user.role === 'admin');

  // Find where admin items start (for showing separator)
  const adminStartIndex = filteredNavItems.findIndex(item => item.adminOnly);

  // Combine nav items with plugin items for final list
  const allNavItems = [...filteredNavItems, ...pluginItems];

  const renderLink = (path: string) => location.pathname === path;

  return (
    <div className="relative min-h-screen overflow-hidden text-slate-100">
      <div className="relative z-10 flex min-h-screen">
        {/* Desktop Sidebar */}
        <aside className="fixed left-0 top-0 hidden lg:flex h-screen w-72 flex-col border-r border-white/10 bg-white/5 backdrop-blur-3xl shadow-[0_8px_32px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.1)]">
          <div className="px-6 pt-10 pb-8">
            <div className="flex items-center gap-3">
              <div className="relative flex h-12 w-12 items-center justify-center rounded-full bg-slate-950-tertiary p-[3px]">
                <img src={logoMark} alt="BalùHost logo" className="h-full w-full rounded-full" />
              </div>
              <div>
                <p className="text-lg font-semibold tracking-wide">BalùHost</p>
                <p className="text-xs uppercase tracking-[0.35em] text-slate-100-tertiary">{formattedVersion}</p>
                <DeveloperBadge />
              </div>
            </div>
          </div>

          <nav className="flex-1 px-4 overflow-y-auto pb-4">
            <div className="space-y-1">
              {allNavItems.map((item, index) => {
                const active = renderLink(item.path);
                const isFirstAdminItem = adminStartIndex >= 0 && index === adminStartIndex;
                return (
                  <div key={item.path}>
                    {/* Admin separator */}
                    {isFirstAdminItem && (
                      <div className="my-3 border-t border-slate-800/50 pt-3">
                        <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                          {t('navigation.admin')}
                        </div>
                      </div>
                    )}
                    <Link
                      to={item.path}
                      className={`group flex items-center gap-3 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all duration-200 ${
                        active
                          ? 'border-sky-500 bg-slate-900-hover text-sky-400'
                          : 'border-transparent text-slate-300'
                      }`}
                    >
                      <span
                        className={`flex h-9 w-9 items-center justify-center rounded-xl border text-base transition-colors duration-200 ${
                          active
                            ? 'border-sky-500/40 bg-slate-950-secondary text-sky-400'
                            : 'border-slate-800 bg-slate-950 text-slate-100-tertiary group-hover:border-sky-500/30 group-hover:text-sky-400'
                        }`}
                      >
                        {item.icon}
                      </span>
                      <div className="flex flex-col">
                        <span className="flex items-center gap-2">
                          {item.label}
                          {item.adminOnly && <AdminBadge />}
                        </span>
                        <span className="text-xs text-slate-100-tertiary">{item.description}</span>
                      </div>
                    </Link>
                  </div>
                );
              })}
            </div>
          </nav>


        </aside>

        {/* Mobile Menu Overlay */}
        {mobileMenuOpen && (
          <div 
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        {/* Mobile Sidebar */}
        <aside className={`fixed left-0 top-0 z-50 h-screen w-72 flex-col border-r border-white/10 bg-slate-900/95 backdrop-blur-3xl shadow-[0_8px_32px_rgba(0,0,0,0.5)] transition-transform duration-300 lg:hidden ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}>
          <div className="flex items-center justify-between px-6 pt-6 pb-4">
            <div className="flex items-center gap-3">
              <div className="relative flex h-10 w-10 items-center justify-center rounded-full bg-slate-950-tertiary p-[3px]">
                <img src={logoMark} alt="BalùHost logo" className="h-full w-full rounded-full" />
              </div>
              <div>
                <p className="text-base font-semibold tracking-wide">BalùHost</p>
                <p className="text-[10px] uppercase tracking-[0.3em] text-slate-100-tertiary">{formattedVersion}</p>
                <DeveloperBadge />
              </div>
            </div>
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition"
            >
              <svg viewBox="0 0 24 24" fill="none" strokeWidth={2} className="h-5 w-5">
                <path stroke="currentColor" strokeLinecap="round" d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <nav className="flex-1 px-4 overflow-y-auto pb-4">
            <div className="space-y-1">
              {allNavItems.map((item, index) => {
                const active = renderLink(item.path);
                const isFirstAdminItem = adminStartIndex >= 0 && index === adminStartIndex;
                return (
                  <div key={`mobile-nav-${item.path}`}>
                    {/* Admin separator */}
                    {isFirstAdminItem && (
                      <div className="my-3 border-t border-slate-800/50 pt-3">
                        <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                          {t('navigation.admin')}
                        </div>
                      </div>
                    )}
                    <Link
                      to={item.path}
                      onClick={() => setMobileMenuOpen(false)}
                      className={`group flex items-center gap-3 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all duration-200 ${
                        active
                          ? 'border-sky-500 bg-slate-900-hover text-sky-400'
                          : 'border-transparent text-slate-300 hover:border-slate-800'
                      }`}
                    >
                      <span
                        className={`flex h-9 w-9 items-center justify-center rounded-xl border text-base transition-colors duration-200 ${
                          active
                            ? 'border-sky-500/40 bg-slate-950-secondary text-sky-400'
                            : 'border-slate-800 bg-slate-950 text-slate-100-tertiary group-hover:border-sky-500/30 group-hover:text-sky-400'
                        }`}
                      >
                        {item.icon}
                      </span>
                      <div className="flex flex-col">
                        <span className="flex items-center gap-2">
                          {item.label}
                          {item.adminOnly && <AdminBadge />}
                        </span>
                        <span className="text-xs text-slate-100-tertiary">{item.description}</span>
                      </div>
                    </Link>
                  </div>
                );
              })}
            </div>
          </nav>

          <div className="px-4 pb-6">
            <div className="glass-accent border-slate-800 bg-slate-900/55">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Logged in as</p>
                  <p className="text-sm font-semibold text-slate-100">{user.username}</p>
                  <p className="text-xs text-slate-100-tertiary">{user.role === 'admin' ? 'Administrator' : 'User'}</p>
                </div>
                <div className="flex h-12 w-12 items-center justify-center rounded-full border border-sky-500/20 bg-sky-500/10 text-lg font-semibold text-sky-400">
                  {user.username.charAt(0).toUpperCase()}
                </div>
              </div>
            </div>
          </div>
        </aside>

        <div className="flex flex-1 flex-col lg:pl-72">
          {shutdownPending && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
              <div className="flex flex-col items-center gap-4 rounded-2xl bg-slate-900/90 border border-slate-800 p-6">
                <div className="h-12 w-12 flex items-center justify-center rounded-full bg-rose-500/10 text-rose-400">
                  <svg className="h-6 w-6 animate-spin" viewBox="0 0 24 24" fill="none" strokeWidth={2}>
                    <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 2v4M12 18v4M4.2 4.2l2.8 2.8M17 17l2.8 2.8M2 12h4M18 12h4M4.2 19.8l2.8-2.8M17 7l2.8-2.8" />
                  </svg>
                </div>
                <div className="text-center">
                  <p className="font-semibold">Shutting down</p>
                  <p className="text-sm text-slate-100-tertiary">{shutdownMessage}</p>
                </div>
              </div>
            </div>
          )}
          <header className="fixed top-0 right-0 left-0 lg:left-72 z-30 border-b border-slate-800/50 bg-slate-900/20 px-4 py-4 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-2xl sm:px-6 lg:px-10">
            <div className="flex items-center justify-between">
              {/* Mobile Header Left */}
              <div className="flex items-center gap-3 lg:hidden">
                <button
                  onClick={() => setMobileMenuOpen(true)}
                  className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition"
                >
                  <svg viewBox="0 0 24 24" fill="none" strokeWidth={2} className="h-5 w-5">
                    <path stroke="currentColor" strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </button>
                <div className="flex items-center gap-2">
                  <div className="relative flex h-8 w-8 items-center justify-center rounded-full bg-slate-950-tertiary p-[2px]">
                    <img src={logoMark} alt="BalùHost" className="h-full w-full rounded-full" />
                  </div>
                  <span className="text-sm font-semibold">BalùHost</span>
                </div>
              </div>

              {/* Desktop Header Left */}
              <div className="hidden lg:flex flex-col items-start">
                <span className="text-sm font-medium text-slate-100">{user.username}</span>
                <span className="text-xs text-slate-100-tertiary">
                  {user.role === 'admin' ? 'Administrator' : 'Standard Access'} - <span className="text-sky-400">Online</span>
                </span>
              </div>

              {/* Header Right */}
              <div className="flex items-center gap-3">
                <NotificationCenter />
                <div className="hidden md:flex h-10 w-10 items-center justify-center rounded-full border border-sky-500/20 bg-sky-500/10 text-sky-400">
                  {user.username.charAt(0).toUpperCase()}
                </div>
                {user.role === 'admin' && (
                  <button
                    onClick={async () => {
                      const ok = window.confirm('Server herunterfahren? Alle Dienste werden beendet. Fortfahren?');
                      if (!ok) return;
                      setShutdownPending(true);
                      setShutdownMessage('Shutdown gestartet — warte auf Bestätigung...');

                      try {
                        const res = await localApi.shutdown();
                        const eta = (res && (res as any).eta_seconds) || 1;
                        setShutdownMessage(`Shutdown geplant — beendet in ~${eta}s`);

                        // Wait for shutdown to complete, then logout
                        setTimeout(() => {
                          setShutdownPending(false);
                          onLogout();
                        }, (eta + 1) * 1000);
                      } catch (err: any) {
                        console.error('Shutdown API call error (may be expected):', err);
                        setShutdownMessage('Server wird heruntergefahren...');

                        // Still logout after a short delay
                        setTimeout(() => {
                          setShutdownPending(false);
                          onLogout();
                        }, 2000);
                      }
                    }}
                    className="rounded-xl border border-rose-600 bg-rose-600/10 px-3 py-2 text-sm font-medium text-rose-400 transition hover:border-rose-500/50 md:px-4"
                  >
                    <span className="hidden sm:inline">Shutdown</span>
                    <span className="sm:hidden">
                      <svg viewBox="0 0 24 24" fill="none" strokeWidth={2} className="h-4 w-4">
                        <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 2v10M6 12h12" />
                      </svg>
                    </span>
                  </button>
                )}
                <button
                  onClick={onLogout}
                  className="rounded-xl border border-slate-800 px-3 py-2 text-sm font-medium text-slate-100 transition hover:border-sky-500/50 hover:text-slate-100 md:px-4"
                >
                  <span className="hidden sm:inline">Logout</span>
                  <span className="sm:hidden">
                    <svg viewBox="0 0 24 24" fill="none" strokeWidth={2} className="h-4 w-4">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
                    </svg>
                  </span>
                </button>
              </div>
            </div>
          </header>

          <main className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-6 sm:px-6 lg:px-10 mt-[72px] pb-[env(safe-area-inset-bottom)]">
            <div className={`${location.pathname === '/admin-db' ? 'w-full max-w-none mx-0' : 'mx-auto w-full max-w-7xl'} space-y-6 sm:space-y-8`}>
              {children}
            </div>
          </main>
          <UploadProgressBar />
        </div>
      </div>
    </div>
  );
}
