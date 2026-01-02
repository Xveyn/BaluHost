import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import FileManager from './pages/FileManager';
import UserManagement from './pages/UserManagement';
import SystemMonitor from './pages/SystemMonitor';
import RaidManagement from './pages/RaidManagement';
import Logging from './pages/Logging';
import ApiCenterPage from './pages/ApiCenterPage';
import SharesPage from './pages/SharesPage';
import SettingsPage from './pages/SettingsPage';
import PublicSharePage from './pages/PublicSharePage';
import AdminDatabase from './pages/AdminDatabase';
import SyncSettings from './components/SyncSettings';
import SyncPrototype from './pages/SyncPrototype';
import MobileDevicesPage from './pages/MobileDevicesPage';
import Layout from './components/Layout';
import { buildApiUrl } from './lib/api';
import './App.css';

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    console.log('App init - token exists:', !!token);
    
    if (token) {
      console.log('Verifying token with /api/auth/me');
      fetch(buildApiUrl('/api/auth/me'), {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
        .then(res => {
          console.log('Auth me response status:', res.status);
          if (!res.ok) {
            throw new Error('Token invalid');
          }
          return res.json();
        })
        .then(data => {
          console.log('User data received:', data);
          if (data.user || data.username) {
            setUser(data.user || data);
          } else {
            throw new Error('Invalid user data');
          }
        })
        .catch((err) => {
          console.error('Token verification failed:', err);
          localStorage.removeItem('token');
          setUser(null);
        })
        .finally(() => {
          setLoading(false);
        });
    } else {
      console.log('No token found, showing login');
      setLoading(false);
    }
  }, []);

  const handleLogin = (userData: User, token: string) => {
    console.log('Login successful - User:', userData);
    console.log('Login successful - Token preview:', token.substring(0, 30) + '...');
    localStorage.setItem('token', token);
    setUser(userData);
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('token');
  };

  const LoadingScreen = () => {
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
            <p className="text-sm uppercase tracking-[0.35em] text-slate-500">BalùHost</p>
            <p className="text-lg font-medium text-white">Loading system insights{dots}</p>
        </div>
      </div>
    );
  };

  if (loading) return <LoadingScreen />;

  return (
    <Router>
      <Routes>
        <Route
          path="/login"
          element={
            user ? <Navigate to="/" /> : <Login onLogin={handleLogin} />
          }
        />
        <Route
          path="/"
          element={
            user ? (
              <Layout user={user} onLogout={handleLogout}>
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
              <Layout user={user} onLogout={handleLogout}>
                <FileManager user={user} />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/users"
          element={
            user?.role === 'admin' ? (
              <Layout user={user} onLogout={handleLogout}>
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
            user?.role === 'admin' ? (
              <Layout user={user} onLogout={handleLogout}>
                <AdminDatabase />
              </Layout>
            ) : (
              <Navigate to="/" />
            )
          }
        />
        <Route
          path="/raid"
          element={
            user?.role === 'admin' ? (
              <Layout user={user} onLogout={handleLogout}>
                <RaidManagement />
              </Layout>
            ) : (
              <Navigate to="/" />
            )
          }
        />
        <Route
          path="/system"
          element={
            user ? (
              <Layout user={user} onLogout={handleLogout}>
                <SystemMonitor />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/logging"
          element={
            user ? (
              <Layout user={user} onLogout={handleLogout}>
                <Logging />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/shares"
          element={
            user ? (
              <Layout user={user} onLogout={handleLogout}>
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
              <Layout user={user} onLogout={handleLogout}>
                <SettingsPage />
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
              <Layout user={user} onLogout={handleLogout}>
                <SyncSettings />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/sync-prototype"
          element={
            user ? (
              <Layout user={user} onLogout={handleLogout}>
                <SyncPrototype />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/mobile-devices"
          element={
            user ? (
              <Layout user={user} onLogout={handleLogout}>
                <MobileDevicesPage />
              </Layout>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
        <Route
          path="/docs"
          element={
            user ? (
              <Layout user={user} onLogout={handleLogout}>
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
      </Routes>
    </Router>
  );
}

export default App;
