import NotificationCenter from '../NotificationCenter';
import PowerMenu from '../PowerMenu';
import UserMenu from '../UserMenu';
import { TopbarStatusStrip } from '../topbar/TopbarStatusStrip';
import { isPi } from '../../lib/features';
import { SidebarBrand } from './SidebarBrand';

interface LayoutHeaderProps {
  isImpersonating: boolean;
  isAdmin: boolean;
  onOpenMobileMenu: () => void;
  onShutdown: () => Promise<void>;
  onRestart: () => Promise<void>;
  onLogout: () => void;
}

export function LayoutHeader({ isImpersonating, isAdmin, onOpenMobileMenu, onShutdown, onRestart, onLogout }: LayoutHeaderProps) {
  return (
    <header className={`fixed right-0 left-0 lg:left-72 z-30 border-b border-slate-800/50 bg-slate-900/20 px-4 py-4 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-2xl sm:px-6 lg:px-10 ${isImpersonating ? 'top-10' : 'top-0'}`}>
      <div className="flex items-center justify-between">
        {/* Mobile Header Left */}
        <div className="flex items-center gap-3 lg:hidden">
          <button
            onClick={onOpenMobileMenu}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition"
          >
            <svg viewBox="0 0 24 24" fill="none" strokeWidth={2} className="h-5 w-5">
              <path stroke="currentColor" strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <SidebarBrand variant="compact" />
        </div>

        {/* Status strip (desktop only, hidden in Pi mode) */}
        <div className="hidden lg:flex flex-1 items-center justify-center px-6">
          {!isPi && <TopbarStatusStrip />}
        </div>

        {/* Header Right */}
        <div className="flex items-center gap-3">
          {!isPi && <NotificationCenter />}
          <UserMenu />
          {isPi ? (
            <button
              onClick={onLogout}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition"
              title="Logout"
            >
              <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
            </button>
          ) : (
            <PowerMenu isAdmin={isAdmin} onShutdown={onShutdown} onRestart={onRestart} onLogout={onLogout} />
          )}
        </div>
      </div>
    </header>
  );
}
