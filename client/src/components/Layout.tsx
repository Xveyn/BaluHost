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
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-slate-100">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 -top-32 h-96 w-96 rounded-full bg-[radial-gradient(circle_at_center,_rgba(56,189,248,0.32),_rgba(2,6,23,0)_60%)] blur-3xl" />
        <div className="absolute -right-32 top-1/4 h-[420px] w-[420px] rounded-full bg-[radial-gradient(circle_at_center,_rgba(124,58,237,0.25),_rgba(2,6,23,0)_62%)] blur-[120px]" />
        <div className="absolute left-1/3 bottom-[-180px] h-[380px] w-[380px] rounded-full bg-[radial-gradient(circle_at_center,_rgba(59,130,246,0.2),_rgba(2,6,23,0)_70%)] blur-[110px]" />
      </div>

      <div className="relative z-10 flex min-h-screen">
        <aside className="hidden lg:flex w-72 flex-col border-r border-slate-800/60 bg-slate-900/40 backdrop-blur-xl">
          <div className="px-6 pt-10 pb-8">
            <div className="flex items-center gap-3">
              <div className="relative flex h-12 w-12 items-center justify-center rounded-full bg-slate-950/60 p-[3px] shadow-[0_18px_45px_rgba(56,189,248,0.25)]">
                <div className="absolute inset-0 -z-10 rounded-full bg-gradient-to-br from-sky-500/50 via-indigo-500/40 to-violet-600/30 blur-sm" />
                <img src={logoMark} alt="BalùHost logo" className="h-full w-full rounded-full" />
              </div>
              <div>
                <p className="text-lg font-semibold tracking-wide">BalùHost</p>
                <p className="text-xs uppercase tracking-[0.35em] text-slate-500">NAS OS v4</p>
              </div>
            </div>
          </div>

          <nav className="flex-1 space-y-2 px-4">
            {navItems.map((item) => {
              const active = renderLink(item.path);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`group flex items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium transition-all duration-200 ${
                    active
                      ? 'border-sky-500/40 bg-gradient-to-r from-sky-500/15 via-indigo-500/10 to-transparent text-white shadow-[0_14px_44px_rgba(56,189,248,0.2)]'
                      : 'border-transparent text-slate-400 hover:border-slate-700/60 hover:bg-slate-900/40 hover:text-white'
                  }`}
                >
                  <span
                    className={`flex h-10 w-10 items-center justify-center rounded-xl border text-base transition-colors duration-200 ${
                      active
                        ? 'border-sky-500/40 bg-slate-900/70 text-sky-200'
                        : 'border-slate-800 bg-slate-950/40 text-slate-400 group-hover:border-sky-500/30 group-hover:text-sky-200'
                    }`}
                  >
                    {item.icon}
                  </span>
                  <div className="flex flex-col">
                    <span>{item.label}</span>
                    <span className="text-xs text-slate-500">{item.description}</span>
                  </div>
                </Link>
              );
            })}
          </nav>

          <div className="px-6 pb-10">
            <div className="glass-accent">
              <p className="text-xs uppercase tracking-[0.3em] text-emerald-300/80">System Healthy</p>
              <div className="mt-4 flex items-center justify-between">
                <div>
                  <p className="text-2xl font-semibold text-emerald-300">99%</p>
                  <p className="text-xs text-slate-400">Storage 70% free</p>
                </div>
                <div className="glow-ring h-16 w-16">
                  <div className="h-[52px] w-[52px] rounded-full bg-[conic-gradient(at_center,_rgba(16,185,129,0.9)_0%,_rgba(16,185,129,0.9)_240deg,_rgba(15,23,42,0.9)_240deg,_rgba(15,23,42,0.9)_360deg)]" />
                </div>
              </div>
            </div>
          </div>
        </aside>

        <div className="flex flex-1 flex-col">
          <header className="border-b border-slate-800/60 bg-slate-900/30 px-6 py-6 shadow-[0_12px_40px_rgba(2,6,23,0.45)] backdrop-blur-xl sm:px-8 lg:px-10">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="hidden md:flex flex-col items-start">
                <span className="text-sm font-medium text-slate-200">{user.username}</span>
                <span className="text-xs text-slate-500">
                  {user.role === 'admin' ? 'Administrator' : 'Standard Access'} - <span className="text-emerald-400">Online</span>
                </span>
              </div>

              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full border border-sky-500/20 bg-sky-500/10 text-sky-200">
                  {user.username.charAt(0).toUpperCase()}
                </div>
                <button
                  onClick={onLogout}
                  className="rounded-xl border border-slate-700/70 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 hover:text-white"
                >
                  Logout
                </button>
              </div>
            </div>

            <div className="mt-4 flex gap-2 overflow-x-auto pb-2 text-sm text-slate-400 lg:hidden">
              {navItems.map((item) => {
                const active = renderLink(item.path);
                return (
                  <Link
                    key={`mobile-${item.path}`}
                    to={item.path}
                    className={`whitespace-nowrap rounded-full border px-3 py-1.5 transition ${
                      active
                        ? 'border-sky-500/40 bg-sky-500/20 text-slate-100'
                        : 'border-slate-800 bg-slate-900/60 hover:border-sky-500/30 hover:text-slate-100'
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </header>

          <main className="flex-1 overflow-y-auto px-6 py-8 sm:px-8 lg:px-10">
            <div className="mx-auto w-full max-w-7xl space-y-8">
              {children}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
