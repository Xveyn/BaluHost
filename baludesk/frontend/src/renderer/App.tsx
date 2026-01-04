import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Sync from './pages/Sync';
import FileExplorer from './pages/FileExplorer';
import Settings from './components/Settings';
import MainLayout from './components/MainLayout';

interface User {
  username: string;
  serverUrl?: string;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check for stored session
    const storedUser = localStorage.getItem('baludesk_user');
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch (e) {
        localStorage.removeItem('baludesk_user');
      }
    }
    setLoading(false);
  }, []);

  const handleLogin = (userData: User) => {
    setUser(userData);
    localStorage.setItem('baludesk_user', JSON.stringify(userData));
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('baludesk_user');
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <div className="text-slate-400">Loading...</div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          className: '',
          style: {
            background: '#1e293b',
            color: '#f1f5f9',
            border: '1px solid #334155',
          },
        }}
      />
      <Routes>
        <Route
          path="/login"
          element={user ? <Navigate to="/" replace /> : <Login onLogin={handleLogin} />}
        />
        
        {/* Protected routes with MainLayout */}
        <Route
          path="/"
          element={
            user ? (
              <MainLayout user={user} onLogout={handleLogout}>
                <Dashboard user={user} onLogout={handleLogout} />
              </MainLayout>
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        
        <Route
          path="/sync"
          element={
            user ? (
              <MainLayout user={user} onLogout={handleLogout}>
                <Sync />
              </MainLayout>
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        
        <Route
          path="/files"
          element={
            user ? (
              <MainLayout user={user} onLogout={handleLogout}>
                <FileExplorer />
              </MainLayout>
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        <Route
          path="/settings"
          element={
            user ? (
              <MainLayout user={user} onLogout={handleLogout}>
                <Settings onClose={() => window.location.href = '/'} />
              </MainLayout>
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
