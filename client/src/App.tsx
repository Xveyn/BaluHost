import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect, lazy, Suspense } from 'react';
// '/index' is required — see Layout.tsx for why a bare './components/layout' silently
// self-resolves to this file's sibling Layout.tsx on Windows (case-insensitive FS).
import { AppLayout } from './components/layout/index';
import { ErrorBoundary } from './components/ErrorBoundary';
import { PluginProvider } from './contexts/PluginContext';
import { VersionProvider } from './contexts/VersionContext';
import { UploadProvider } from './contexts/UploadContext';
import { NotificationProvider } from './contexts/NotificationContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { buildApiUrl } from './lib/api';
import { useIdleTimeout } from './hooks/useIdleTimeout';
import { IdleWarningDialog } from './components/ui/IdleWarningDialog';
import { usePresenceHeartbeat } from './hooks/usePresenceHeartbeat';
import { FEATURES, isDesktop } from './lib/features';
import { LoadingFallback } from './components/ui/LoadingFallback';
import logoMark from './assets/baluhost-logo.png';
import './App.css';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function lazyWithRetry(importFn: () => Promise<{ default: React.ComponentType<any> }>) {
  return lazy(async () => {
    try {
      return await importFn();
    } catch (error) {
      if (!sessionStorage.getItem('chunk-reload')) {
        sessionStorage.setItem('chunk-reload', '1');
        window.location.reload();
      }
      throw error;
    }
  });
}

// Pages available on both desktop and Pi
const Login = lazyWithRetry(() => import('./pages/Login'));
const Dashboard = lazyWithRetry(() => import('./pages/Dashboard'));
const SystemMonitor = lazyWithRetry(() => import('./pages/SystemMonitor'));

// Desktop-only pages — NOT bundled in Pi builds (tree-shaken via __DEVICE_MODE__)
const FileManager = isDesktop ? lazyWithRetry(() => import('./pages/FileManager')) : null;
const UserManagement = isDesktop ? lazyWithRetry(() => import('./pages/UserManagement')) : null;
const SchedulerDashboard = isDesktop ? lazyWithRetry(() => import('./pages/SchedulerDashboard')) : null;
const UserManualPage = isDesktop ? lazyWithRetry(() => import('./pages/UserManualPage')) : null;
const SharesPage = isDesktop ? lazyWithRetry(() => import('./pages/SharesPage')) : null;
const SettingsPage = isDesktop ? lazyWithRetry(() => import('./pages/SettingsPage')) : null;
const AdminDatabase = isDesktop ? lazyWithRetry(() => import('./pages/AdminDatabase')) : null;
const DevicesPage = isDesktop ? lazyWithRetry(() => import('./pages/DevicesPage')) : null;
const SystemControlPage = isDesktop ? lazyWithRetry(() => import('./pages/SystemControlPage')) : null;
const PluginsPage = isDesktop ? lazyWithRetry(() => import('./pages/PluginsPage')) : null;
const NotificationsArchivePage = isDesktop ? lazyWithRetry(() => import('./pages/NotificationsArchivePage')) : null;
const UpdatePage = isDesktop ? lazyWithRetry(() => import('./pages/UpdatePage')) : null;
const CloudImportPage = isDesktop ? lazyWithRetry(() => import('./pages/CloudImportPage')) : null;
const PiholePage = isDesktop ? lazyWithRetry(() => import('./pages/PiholePage')) : null;
const SmartDevicesPage = isDesktop ? lazyWithRetry(() => import('./pages/SmartDevicesPage')) : null;
const PluginPage = isDesktop ? lazyWithRetry(() => import('./components/PluginPage')) : null;

// Pi-only pages — NOT bundled in desktop builds
const PiDashboard = FEATURES.piDashboard ? lazyWithRetry(() => import('./pages/PiDashboard')) : null;

const SetupWizard = lazyWithRetry(() => import('./pages/SetupWizard'));

function LoadingScreen({ backendReady, backendCheckAttempts }: { backendReady: boolean; backendCheckAttempts: number }) {
  const [dots, setDots] = useState('');
  useEffect(() => {
    const sequence = ['.', '..', '...', '.', '..'];
    let idx = 0;
    const timer = setInterval(() => {
      setDots(sequence[idx]);
      idx = (idx + 1) % sequence.length;
    }, 450);
    return () => clearInterval(timer);
  }, []);

  const getMessage = () => {
    if (!backendReady) {
      if (backendCheckAttempts === 0) {
        return 'Connecting to backend';
      } else if (backendCheckAttempts < 5) {
        return 'Backend starting';
      } else if (backendCheckAttempts < 10) {
        return 'Waiting for backend services';
      } else if (backendCheckAttempts < 40) {
        return 'Backend initialization in progress';
      } else {
        return 'Backend timeout - trying anyway';
      }
    }
    return 'Loading system insights';
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden text-slate-100">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 -top-24 h-80 w-80 rounded-full bg-[radial-gradient(circle_at_center,_rgba(56,189,248,0.25),_rgba(2,6,23,0)_60%)] blur-3xl" />
        <div className="absolute right-[-120px] top-1/3 h-96 w-96 rounded-full bg-[radial-gradient(circle_at_center,_rgba(124,58,237,0.22),_rgba(2,6,23,0)_60%)] blur-[130px]" />
      </div>
      <div className="relative z-10 flex w-80 flex-col items-center gap-4 rounded-2xl border border-slate-800/60 bg-slate-900/70 px-10 py-8 shadow-[0_18px_55px_rgba(2,6,23,0.55)] backdrop-blur-xl">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-950 p-[2px] shadow-xl">
          <img src={logoMark} alt="BaluHost logo" className="h-full w-full rounded-full" />
        </div>
        <p className="text-sm uppercase tracking-[0.35em] text-slate-500">BaluHost</p>
        <p className="text-lg font-medium text-white">{getMessage()}{dots}</p>
        {!backendReady && backendCheckAttempts < 40 && (
          <div className="mt-2 flex flex-col items-center gap-2">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
              <span className="text-xs text-slate-400">
                Attempt {backendCheckAttempts + 1}/40
              </span>
            </div>
            {backendCheckAttempts > 10 && backendCheckAttempts < 40 && (
              <p className="text-xs text-slate-500 mt-2 max-w-xs text-center">
                Backend is taking longer than usual. Please ensure the server is running.
              </p>
            )}
          </div>
        )}
        {!backendReady && backendCheckAttempts >= 40 && (
          <div className="mt-2 flex flex-col items-center gap-2">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-rose-400" />
              <span className="text-xs text-rose-400">
                Backend did not respond
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-2 max-w-xs text-center">
              Proceeding to login anyway. If login fails, check if the backend is running.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export function AppRoutes() {
  const { user, logout, loading, isAdmin } = useAuth();

  const { warningVisible, secondsRemaining, resetTimer } = useIdleTimeout({
    onLogout: logout,
    enabled: user !== null,
  });

  usePresenceHeartbeat({ paused: warningVisible, enabled: user !== null });

  // Show loading screen while AuthProvider is verifying the stored token
  if (loading) return <LoadingScreen backendReady={true} backendCheckAttempts={0} />;

  return (
    <ErrorBoundary>
    <IdleWarningDialog
      open={warningVisible}
      secondsRemaining={secondsRemaining}
      onStayLoggedIn={resetTimer}
      onLogoutNow={logout}
    />
    <VersionProvider>
    <PluginProvider>
    <Router>
      <UploadProvider>
      <NotificationProvider>
      <Suspense fallback={<LoadingFallback />}>
      <Routes>
        <Route
          path="/login"
          element={user ? <Navigate to="/" /> : <Login />}
        />

        <Route element={user ? <AppLayout /> : <Navigate to="/login" replace />}>
          <Route path="/" element={PiDashboard ? <PiDashboard /> : <Dashboard />} />
          <Route path="/system" element={<SystemMonitor />} />

          {/* Desktop-only routes (not bundled in Pi builds) */}
          {FileManager && <Route path="/files" element={<FileManager />} />}
          {UserManagement && <Route path="/users" element={isAdmin ? <UserManagement /> : <Navigate to="/" />} />}
          {AdminDatabase && <Route path="/admin-db" element={isAdmin ? <AdminDatabase /> : <Navigate to="/" />} />}
          {SchedulerDashboard && <Route path="/schedulers" element={isAdmin ? <SchedulerDashboard /> : <Navigate to="/" />} />}
          {SharesPage && <Route path="/shares" element={<SharesPage />} />}
          {SettingsPage && <Route path="/settings" element={<SettingsPage />} />}
          {DevicesPage && <Route path="/devices" element={<DevicesPage />} />}
          {SystemControlPage && <Route path="/admin/system-control" element={isAdmin ? <SystemControlPage /> : <Navigate to="/" />} />}
          {NotificationsArchivePage && <Route path="/notifications" element={<NotificationsArchivePage />} />}
          {UserManualPage && <Route path="/manual" element={<UserManualPage />} />}
          {PluginsPage && <Route path="/plugins" element={isAdmin ? <PluginsPage /> : <Navigate to="/" />} />}
          {PluginPage && <Route path="/plugins/:pluginName/*" element={<PluginPage />} />}
          {UpdatePage && <Route path="/updates" element={isAdmin ? <UpdatePage /> : <Navigate to="/" />} />}
          {CloudImportPage && <Route path="/cloud-import" element={<CloudImportPage />} />}
          {PiholePage && <Route path="/pihole" element={isAdmin ? <PiholePage /> : <Navigate to="/" />} />}
          {SmartDevicesPage && <Route path="/smart-devices" element={<SmartDevicesPage />} />}
        </Route>

        {/* Redirects bleiben unverändert außerhalb der Layout-Route */}
        {isDesktop && <Route path="/settings/notifications" element={<Navigate to="/settings?tab=notifications" replace />} />}
        {isDesktop && <Route path="/notifications/settings" element={<Navigate to="/settings?tab=notifications" replace />} />}
        {isDesktop && <Route path="/docs" element={<Navigate to="/manual" replace />} />}
        {isDesktop && <Route path="/raid" element={<Navigate to="/admin/system-control?tab=raid" replace />} />}
        {isDesktop && <Route path="/health" element={<Navigate to="/system?tab=health" replace />} />}
        {isDesktop && <Route path="/power" element={<Navigate to="/admin/system-control?tab=energy" replace />} />}
        {isDesktop && <Route path="/fan-control" element={<Navigate to="/admin/system-control?tab=fan" replace />} />}
        {isDesktop && <Route path="/logging" element={<Navigate to="/system?tab=logs" replace />} />}
        {isDesktop && <Route path="/sync-prototype" element={<Navigate to="/devices?tab=desktop" replace />} />}
        {isDesktop && <Route path="/mobile-devices" element={<Navigate to="/devices?tab=mobile" replace />} />}
        {isDesktop && <Route path="/admin/backup" element={<Navigate to="/admin/system-control?tab=backup" replace />} />}
        {isDesktop && <Route path="/admin/vpn" element={<Navigate to="/admin/system-control?tab=vpn" replace />} />}
        {isDesktop && <Route path="/backups" element={<Navigate to="/admin/system-control?tab=backup" replace />} />}
      </Routes>
      </Suspense>
      </NotificationProvider>
      </UploadProvider>
    </Router>
    </PluginProvider>
    </VersionProvider>
    </ErrorBoundary>
  );
}

function App() {
  const [backendReady, setBackendReady] = useState(false);
  const [backendCheckAttempts, setBackendCheckAttempts] = useState(0);
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);

  // Clear stale-chunk reload flag on successful app mount
  useEffect(() => { sessionStorage.removeItem('chunk-reload'); }, []);

  // Check if backend is ready before showing login
  useEffect(() => {
    let isMounted = true;
    let timeoutId: ReturnType<typeof setTimeout>;
    let attemptCount = 0;
    const MAX_ATTEMPTS = 40; // Max 40 attempts = 80 seconds
    const RETRY_INTERVAL = 2000; // 2 seconds between attempts

    const checkBackendHealth = async () => {
      // Stop if max attempts reached
      if (attemptCount >= MAX_ATTEMPTS) {
        if (isMounted) {
          setBackendReady(true); // Show login anyway after timeout
          setSetupRequired(false); // Assume setup done on timeout
        }
        return;
      }

      attemptCount++;
      if (isMounted) {
        setBackendCheckAttempts(attemptCount);
      }

      try {
        // Try health endpoint with short timeout
        const controller = new AbortController();
        const timeoutMs = 2000;
        const timeout = setTimeout(() => controller.abort(), timeoutMs);

        const response = await fetch(buildApiUrl('/api/health'), {
          signal: controller.signal,
          headers: {
            'Accept': 'application/json'
          }
        });

        clearTimeout(timeout);

        if (response.ok && isMounted) {
          setBackendReady(true);
          try {
            const { getSetupStatus } = await import('./api/setup');
            const status = await getSetupStatus();
            if (isMounted) setSetupRequired(status.setup_required);
          } catch {
            if (isMounted) setSetupRequired(false); // On error, assume setup done
          }
          return;
        }
      } catch {
        // Backend not ready yet
      }

      // Schedule next check if we haven't reached max attempts
      if (isMounted && attemptCount < MAX_ATTEMPTS) {
        timeoutId = setTimeout(checkBackendHealth, RETRY_INTERVAL);
      }
    };

    // Start the first check immediately
    checkBackendHealth();

    return () => {
      isMounted = false;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, []); // Empty dependency array - only run once on mount

  // Show loading screen if backend is not ready or setup status is pending
  if (!backendReady || setupRequired === null) return <LoadingScreen backendReady={backendReady} backendCheckAttempts={backendCheckAttempts} />;

  if (setupRequired) {
    return (
      <Suspense fallback={<LoadingFallback />}>
        <SetupWizard onComplete={() => setSetupRequired(false)} />
      </Suspense>
    );
  }

  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}

export default App;
