import { Link, useLocation } from 'react-router-dom';
import { type ReactNode } from 'react';
import logoMark from '../assets/baluhost-logo.svg';

interface LayoutProps {
  children: ReactNode;
  user: {
    username: string;
    role: string;
  };
  onLogout: () => void;
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
  )
} as const;

export default function Layout({ children, user, onLogout }: LayoutProps) {
  const location = useLocation();

  const navItems = [
    {
      path: '/',
      label: 'Dashboard',
      description: 'System overview',
      icon: navIcon.dashboard
    },
    {
      path: '/files',
      label: 'File Manager',
      description: 'Storage & sync',
      icon: navIcon.files
    },
    {
      path: '/system',
      label: 'Disk Monitor',
      description: 'Activity',
      icon: navIcon.system
    },
    {
      path: '/logging',
      label: 'Logging',
      description: 'Activity Logs',
      icon: navIcon.logging
    },
    {
      path: '/shares',
      label: 'Sharing',
      description: 'Share Files',
      icon: navIcon.shares
    },
    {
      path: '/settings',
      label: 'Settings',
      description: 'Account',
      icon: navIcon.settings
    },
    {
      path: '/docs',
      label: 'API Docs',
      description: 'REST API',
      icon: navIcon.docs
    },
    ...(user.role === 'admin'
      ? [
          {
            path: '/raid',
            label: 'RAID Control',
            description: 'Arrays & Health',
            icon: navIcon.raid
          },
          {
            path: '/users',
            label: 'User Access',
            description: 'Permissions',
            icon: navIcon.users
          }
        ]
      : [])
  ];

  const renderLink = (path: string) => location.pathname === path;

  return (
    <div className="relative min-h-screen overflow-hidden text-slate-100">
      <div className="relative z-10 flex min-h-screen">
        <aside className="fixed left-0 top-0 hidden lg:flex h-screen w-72 flex-col border-r border-white/10 bg-white/5 backdrop-blur-3xl shadow-[0_8px_32px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.1)]">
          <div className="px-6 pt-10 pb-8">
            <div className="flex items-center gap-3">
              <div className="relative flex h-12 w-12 items-center justify-center rounded-full bg-slate-950-tertiary p-[3px]">
                <img src={logoMark} alt="BalùHost logo" className="h-full w-full rounded-full" />
              </div>
              <div>
                <p className="text-lg font-semibold tracking-wide">BalùHost</p>
                <p className="text-xs uppercase tracking-[0.35em] text-slate-100-tertiary">NAS OS v4</p>
              </div>
            </div>
          </div>

          <nav className="flex-1 space-y-2 px-4 overflow-y-auto">
            {navItems.map((item) => {
              const active = renderLink(item.path);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`group flex items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium transition-all duration-200 ${
                    active
                      ? 'border-sky-500 bg-slate-900-hover text-sky-400'
                      : 'border-transparent text-slate-300'
                  }`}
                >
                  <span
                    className={`flex h-10 w-10 items-center justify-center rounded-xl border text-base transition-colors duration-200 ${
                      active
                        ? 'border-sky-500/40 bg-slate-950-secondary text-sky-400'
                        : 'border-slate-800 bg-slate-950 text-slate-100-tertiary group-hover:border-sky-500/30 group-hover:text-sky-400'
                    }`}
                  >
                    {item.icon}
                  </span>
                  <div className="flex flex-col">
                    <span>{item.label}</span>
                    <span className="text-xs text-slate-100-tertiary">{item.description}</span>
                  </div>
                </Link>
              );
            })}
          </nav>

          <div className="px-6 pb-10">
            <div className="glass-accent border-slate-800 bg-slate-900/55">
              <p className="text-xs uppercase tracking-[0.3em] text-sky-400">System Healthy</p>
              <div className="mt-4 flex items-center justify-between">
                <div>
                  <p className="text-2xl font-semibold text-sky-400">99%</p>
                  <p className="text-xs text-slate-100-tertiary">Storage 70% free</p>
                </div>
                <div className="glow-ring h-16 w-16">
                  <div className="h-[52px] w-[52px] rounded-full bg-gradient-to-r from-sky-500 via-theme-accent to-theme-bg" />
                </div>
              </div>
            </div>
          </div>
        </aside>

        <div className="flex flex-1 flex-col lg:pl-72">
          <header className="fixed top-0 right-0 left-0 lg:left-72 z-20 border-b border-slate-800/50 bg-slate-900/20 px-6 py-6 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-2xl sm:px-8 lg:px-10">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="hidden md:flex flex-col items-start">
                <span className="text-sm font-medium text-slate-100">{user.username}</span>
                <span className="text-xs text-slate-100-tertiary">
                  {user.role === 'admin' ? 'Administrator' : 'Standard Access'} - <span className="text-sky-400">Online</span>
                </span>
              </div>

              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full border border-sky-500/20 bg-sky-500/10 text-sky-400">
                  {user.username.charAt(0).toUpperCase()}
                </div>
                <button
                  onClick={onLogout}
                  className="rounded-xl border border-slate-800 px-4 py-2 text-sm font-medium text-slate-100 transition hover:border-sky-500/50 hover:text-slate-100"
                >
                  Logout
                </button>
              </div>
            </div>

            <div className="mt-4 flex gap-2 overflow-x-auto pb-2 text-sm text-slate-100-secondary lg:hidden">
              {navItems.map((item) => {
                const active = renderLink(item.path);
                return (
                  <Link
                    key={`mobile-${item.path}`}
                    to={item.path}
                    className={`whitespace-nowrap rounded-full border px-3 py-1.5 transition ${
                      active
                        ? 'border-sky-500 bg-sky-500/20 text-slate-100'
                        : 'border-slate-800 bg-slate-950-secondary text-slate-100-secondary hover:border-sky-500/30 hover:text-slate-100'
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </header>

          <main className="flex-1 overflow-y-auto px-6 py-8 sm:px-8 lg:px-10 mt-[140px] md:mt-[120px]">
            <div className="mx-auto w-full max-w-7xl space-y-8">
              {children}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
