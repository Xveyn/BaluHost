import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { SidebarBrand } from './SidebarBrand';
import { SidebarNav } from './SidebarNav';
import type { LayoutNavItem } from './layoutNavConfig';

interface MobileSidebarProps {
  open: boolean;
  onClose: () => void;
  isImpersonating: boolean;
  items: LayoutNavItem[];
  adminStartIndex: number;
  username?: string;
  isAdmin: boolean;
}

export function MobileSidebar({ open, onClose, isImpersonating, items, adminStartIndex, username, isAdmin }: MobileSidebarProps) {
  const location = useLocation();

  // Before the Task 6 persistent layout route, navigating remounted Layout and the
  // mobile menu reset to closed as a side effect of that remount. With a single
  // persistent route the component no longer remounts on navigation, so this effect
  // makes the close explicit. It also fires once on mount (closing an
  // already-closed menu) — harmless, and accounted for in the test via
  // `onClose.mockClear()`.
  useEffect(() => {
    onClose();
  }, [location.pathname, onClose]);

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      )}
      <aside className={`fixed left-0 z-50 w-72 flex flex-col border-r border-white/10 bg-slate-900/95 backdrop-blur-3xl shadow-[0_8px_32px_rgba(0,0,0,0.5)] transition-transform duration-300 lg:hidden ${
        open ? 'translate-x-0' : '-translate-x-full'
      } ${isImpersonating ? 'top-10 h-[calc(100vh-2.5rem)]' : 'top-0 h-screen'}`}>
        <div className="flex items-center justify-between px-6 pt-6 pb-4">
          <SidebarBrand variant="mobile" />
          <button
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition"
          >
            <svg viewBox="0 0 24 24" fill="none" strokeWidth={2} className="h-5 w-5">
              <path stroke="currentColor" strokeLinecap="round" d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav className="flex-1 px-4 overflow-y-auto scrollbar-thin pb-4">
          <SidebarNav items={items} adminStartIndex={adminStartIndex} variant="mobile" onNavigate={onClose} />
        </nav>

        <div className="px-4 pb-6">
          <div className="glass-accent border-slate-800 bg-slate-900/55">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-400">Logged in as</p>
                <p className="text-sm font-semibold text-slate-100">{username}</p>
                <p className="text-xs text-slate-100-tertiary">{isAdmin ? 'Administrator' : 'User'}</p>
              </div>
              <div className="flex h-12 w-12 items-center justify-center rounded-full border border-sky-500/20 bg-sky-500/10 text-lg font-semibold text-sky-400">
                {username?.charAt(0).toUpperCase()}
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
