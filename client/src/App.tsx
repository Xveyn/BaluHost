import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect, lazy, Suspense } from 'react';
import SyncSettings from './components/SyncSettings';
import PluginPage from './components/PluginPage';
import Layout from './components/Layout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { PluginProvider } from './contexts/PluginContext';
import { VersionProvider } from './contexts/VersionContext';
import { UploadProvider } from './contexts/UploadContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { buildApiUrl } from './lib/api';
import { useIdleTimeout } from './hooks/useIdleTimeout';
import { IdleWarningDialog } from './components/ui/IdleWarningDialog';
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

const Login = lazyWithRetry(() => import('./pages/Login'));
const Dashboard = lazyWithRetry(() => import('./pages/Dashboard'));
const FileManager = lazyWithRetry(() => import('./pages/FileManager'));
const UserManagement = lazyWithRetry(() => import('./pages/UserManagement'));
const SystemMonitor = lazyWithRetry(() => import('./pages/SystemMonitor'));
const SchedulerDashboard = lazyWithRetry(() => import('./pages/SchedulerDashboard'));
const ApiCenterPage = lazyWithRetry(() => import('./pages/ApiCenterPage'));
const SharesPage = lazyWithRetry(() => import('./pages/SharesPage'));
const SettingsPage = lazyWithRetry(() => import('./pages/SettingsPage'));
const PublicSharePage = lazyWithRetry(() => import('./pages/PublicSharePage'));
const AdminDatabase = lazyWithRetry(() => import('./pages/AdminDatabase'));
const DevicesPage = lazyWithRetry(() => import('./pages/DevicesPage'));
const SystemControlPage = lazyWithRetry(() => import('./pages/SystemControlPage'));
const PluginsPage = lazyWithRetry(() => import('./pages/PluginsPage'));
const NotificationPreferencesPage = lazyWithRetry(() => import('./pages/NotificationPreferencesPage'));
const UpdatePage = lazyWithRetry(() => import('./pages/UpdatePage'));
const CloudImportPage = lazyWithRetry(() => import('./pages/CloudImportPage'));

function LoadingFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-sky-500" />
        <p className="text-sm text-slate-500">Loading...</p>
      </div>
    </div>
  );
}

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
      <div className="relative z-10 flex flex-col items-center gap-4 rounded-2xl border border-slate-800/60 bg-slate-900/70 px-10 py-8 shadow-[0_18px_55px_rgba(2,6,23,0.55)] backdrop-blur-xl">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-500 via-indigo-500 to-violet-600 text-xl font-semibold">
          BH
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

function AppRoutes() {
  const { user, logout, loading, isAdmin } = useAuth();

  const { warningVisible, secondsRemaining, resetTimer } = useIdleTimeout({
    onLogout: logout,
    enabled: user !== null,
  });

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
      <Suspense fallback={<LoadingFallback />}>
      <Routes>
        <Route
          path="/login"
          element={
            user ? <Navigate to="/" /> : <Login />
          }
        />
        <Route
          path="/"
          element={
            user ? (
              <Layout>
                <Dashboard />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/files"
          element={
            user ? (
              <Layout>
                <FileManager user={user!} />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/users"
          element={
            isAdmin ? (
              <Layout>
                <UserManagement />
              </Layout>
            ) : (
              <Navigate to="/" />
            )
          }
        />
        <Route
          path="/admin-db"
          element={
            isAdmin ? (
              <Layout>
                <AdminDatabase />
              </Layout>
            ) : (
              <Navigate to="/" />
            )
          }
        />
        {/* Redirect: /raid -> /admin/system-control?tab=raid */}
        <Route
          path="/raid"
          element={<Navigate to="/admin/system-control?tab=raid" replace />}
        />
        <Route
          path="/schedulers"
          element={
            isAdmin ? (
              <Layout>
                <SchedulerDashboard />
              </Layout>
            ) : (
              <Navigate to="/" />
            )
          }
        />
        {/* Redirect: /health -> /system?tab=health */}
        <Route
          path="/health"
          element={<Navigate to="/system?tab=health" replace />}
        />
        <Route
          path="/system"
          element={
            user ? (
              <Layout>
                <SystemMonitor />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        {/* Redirect: /power -> /admin/system-control?tab=energy */}
        <Route
          path="/power"
          element={<Navigate to="/admin/system-control?tab=energy" replace />}
        />
        {/* Redirect: /fan-control -> /admin/system-control?tab=fan */}
        <Route
          path="/fan-control"
          element={<Navigate to="/admin/system-control?tab=fan" replace />}
        />
        {/* Redirect: /logging -> /system?tab=logs */}
        <Route
          path="/logging"
          element={<Navigate to="/system?tab=logs" replace />}
        />
        <Route
          path="/shares"
          element={
            user ? (
              <Layout>
                <SharesPage />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/settings"
          element={
            user ? (
              <Layout>
                <SettingsPage />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/devices"
          element={
            user ? (
              <Layout>
                <DevicesPage />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/admin/system-control"
          element={
            isAdmin ? (
              <Layout>
                <SystemControlPage />
              </Layout>
            ) : (
              <Navigate to="/" />
            )
          }
        />
        <Route
          path="/settings/notifications"
          element={
            user ? (
              <Layout>
                <NotificationPreferencesPage />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/notifications"
          element={
            user ? (
              <Layout>
                <NotificationPreferencesPage />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/sync"
          element={
            user ? (
              <Layout>
                <SyncSettings />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        {/* Redirect: /sync-prototype -> /devices?tab=desktop */}
        <Route
          path="/sync-prototype"
          element={<Navigate to="/devices?tab=desktop" replace />}
        />
        {/* Redirect: /mobile-devices -> /devices?tab=mobile */}
        <Route
          path="/mobile-devices"
          element={<Navigate to="/devices?tab=mobile" replace />}
        />
        {/* Redirect: /admin/backup -> /admin/system-control?tab=backup */}
        <Route
          path="/admin/backup"
          element={<Navigate to="/admin/system-control?tab=backup" replace />}
        />
        {/* Redirect: /admin/vpn -> /admin/system-control?tab=vpn */}
        <Route
          path="/admin/vpn"
          element={<Navigate to="/admin/system-control?tab=vpn" replace />}
        />
        <Route
          path="/docs"
          element={
            user ? (
              <Layout>
                <ApiCenterPage />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/share/:token"
          element={<PublicSharePage />}
        />
        <Route
          path="/plugins"
          element={
            isAdmin ? (
              <Layout>
                <PluginsPage />
              </Layout>
            ) : (
              <Navigate to="/" />
            )
          }
        />
        <Route
          path="/plugins/:pluginName/*"
          element={
            user ? (
              <Layout>
                <PluginPage />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/updates"
          element={
            isAdmin ? (
              <Layout>
                <UpdatePage />
              </Layout>
            ) : (
              <Navigate to="/" />
            )
          }
        />
        <Route
          path="/cloud-import"
          element={
            user ? (
              <Layout>
                <CloudImportPage />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
      </Routes>
      </Suspense>
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

  // Show loading screen if backend is not ready
  if (!backendReady) return <LoadingScreen backendReady={backendReady} backendCheckAttempts={backendCheckAttempts} />;

  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}

export default App;
