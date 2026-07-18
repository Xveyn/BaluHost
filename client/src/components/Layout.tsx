import { useLocation } from 'react-router-dom';
import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getStatusBarState } from '../api/statusBar';
import { isPi } from '../lib/features';
import { UploadProgressBar } from './UploadProgressBar';
import ImpersonationBanner from './ImpersonationBanner';
import { useLayoutNav } from '../hooks/useLayoutNav';
import { usePowerActions } from '../hooks/usePowerActions';
import { DesktopSidebar, MobileSidebar, LayoutHeader, PendingPowerOverlay } from './layout/index';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const { user, logout, isAdmin, isImpersonating } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showUploadBar, setShowUploadBar] = useState(true);
  const { allNavItems, adminStartIndex } = useLayoutNav();
  const { pendingAction, pendingMessage, onShutdown, onRestart } = usePowerActions(logout);

  // Auf pathname gekeyt: refetcht wie vor der Layout-Route bei jeder Navigation,
  // sonst bliebe show_bottom_upload nach einer Einstellungsänderung stale
  // (Spec-Delta Nr. 2).
  useEffect(() => {
    let cancelled = false;
    getStatusBarState()
      .then((s) => { if (!cancelled) setShowUploadBar(s.show_bottom_upload); })
      .catch(() => { /* default to showing on error */ });
    return () => { cancelled = true; };
  }, [location.pathname]);

  const closeMobileMenu = useCallback(() => setMobileMenuOpen(false), []);

  return (
    <div className="relative min-h-screen overflow-x-hidden text-slate-100">
      <div className="relative z-10 flex min-h-screen">
        <DesktopSidebar isImpersonating={isImpersonating} items={allNavItems} adminStartIndex={adminStartIndex} />
        <MobileSidebar
          open={mobileMenuOpen}
          onClose={closeMobileMenu}
          isImpersonating={isImpersonating}
          items={allNavItems}
          adminStartIndex={adminStartIndex}
          username={user?.username}
          isAdmin={isAdmin}
        />
        <div className="flex flex-1 flex-col lg:pl-72 overflow-x-hidden">
          <PendingPowerOverlay action={pendingAction} message={pendingMessage} />
          <ImpersonationBanner />
          <LayoutHeader
            isImpersonating={isImpersonating}
            isAdmin={isAdmin}
            onOpenMobileMenu={() => setMobileMenuOpen(true)}
            onShutdown={onShutdown}
            onRestart={onRestart}
            onLogout={logout}
          />
          <main className={`flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-10 pb-[env(safe-area-inset-bottom)] ${isImpersonating ? 'mt-[112px]' : 'mt-[72px]'}`}>
            <div className={`${location.pathname === '/admin-db' ? 'w-full max-w-none mx-0' : 'mx-auto w-full max-w-7xl'} space-y-6 sm:space-y-8`}>
              {children}
            </div>
          </main>
          {!isPi && showUploadBar && <UploadProgressBar />}
        </div>
      </div>
    </div>
  );
}
