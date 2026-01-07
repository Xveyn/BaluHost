import { useState, FormEvent } from 'react';
import toast from 'react-hot-toast';
import { ServerSelector } from '../components/Login/ServerSelector';
import type { RemoteServerProfile } from '../types/RemoteServerProfile';

interface LoginProps {
  onLogin: (user: any) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [serverUrl, setServerUrl] = useState('https://localhost:8000');
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  const [useServerSelection, setUseServerSelection] = useState(true);
  const [loading, setLoading] = useState(false);

  const handleSelectProfile = (profile: RemoteServerProfile) => {
    setSelectedProfileId(profile.id);
    // Build server URL from profile SSH host with BaluHost HTTP port (8000)
    const url = `http://${profile.sshHost}:8000`;
    setServerUrl(url);
    // Auto-fill username from profile if available
    if (profile.sshUsername && !username) {
      setUsername(profile.sshUsername);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    
    if (!serverUrl.trim()) {
      toast.error('Please select or enter a server URL');
      return;
    }

    setLoading(true);

    try {
      // Send login command to C++ backend via Electron IPC
      const response = await window.electronAPI.sendBackendCommand({
        type: 'login',
        data: {
          username,
          password,
          serverUrl,
          profileId: selectedProfileId, // Pass selected profile ID if available
        },
      });

      if (response.success) {
        toast.success('Login successful!');
        // Store user with profile selection
        const userData = { 
          username, 
          serverUrl,
          selectedProfileId, 
        };
        onLogin(userData);
      } else {
        toast.error(response.error || 'Login failed');
      }
    } catch (err: any) {
      console.error('Login error:', err);
      toast.error(err.message || 'Failed to connect to backend');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden text-slate-100">
      {/* Animated background gradients */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 top-[-120px] h-[420px] w-[420px] rounded-full bg-sky-500/10 blur-3xl" />
        <div className="absolute right-[-120px] top-[18%] h-[460px] w-[460px] rounded-full bg-sky-500/10 blur-[140px]" />
        <div className="absolute left-[45%] bottom-[-180px] h-[340px] w-[340px] rounded-full bg-sky-500/5 blur-[120px]" />
      </div>

      <div className="relative z-10 w-full max-w-md px-4 sm:px-6">
        <div className="card border border-slate-800 bg-slate-900/55 p-6 sm:p-10">
          <div className="flex flex-col items-center text-center">
            <div className="glow-ring h-14 w-14 sm:h-16 sm:w-16">
              <div className="flex h-12 w-12 sm:h-14 sm:w-14 items-center justify-center rounded-full bg-slate-950 p-[2px] shadow-xl">
                <svg
                  className="h-8 w-8 text-sky-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"
                  />
                </svg>
              </div>
            </div>
            <h1 className="mt-5 sm:mt-6 text-2xl sm:text-3xl font-semibold tracking-wide text-slate-100">
              BaluDesk
            </h1>
            <p className="mt-2 text-sm text-slate-400">Desktop Sync Client</p>
          </div>

          <form onSubmit={handleSubmit} className="mt-8 sm:mt-10 space-y-4 sm:space-y-5">
            {/* Server Selection Mode Toggle */}
            {useServerSelection ? (
              <ServerSelector
                selectedProfileId={selectedProfileId}
                onSelectProfile={handleSelectProfile}
                onManualMode={() => {
                  setUseServerSelection(false);
                  setSelectedProfileId(null);
                }}
              />
            ) : (
              <>
                <div className="space-y-2">
                  <label
                    htmlFor="serverUrl"
                    className="text-xs font-medium uppercase tracking-[0.2em] text-slate-400"
                  >
                    Server URL
                  </label>
                  <input
                    type="text"
                    id="serverUrl"
                    className="input"
                    value={serverUrl}
                    onChange={(e) => setServerUrl(e.target.value)}
                    placeholder="https://localhost:8000"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setUseServerSelection(true)}
                    className="text-xs text-slate-400 hover:text-slate-300"
                  >
                    Or select from saved servers
                  </button>
                </div>
              </>
            )}

            <div className="space-y-2">
              <label
                htmlFor="username"
                className="text-xs font-medium uppercase tracking-[0.2em] text-slate-400"
              >
                Username
              </label>
              <input
                type="text"
                id="username"
                className="input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
                required
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-medium uppercase tracking-[0.2em] text-slate-400">
                <label htmlFor="password">Password</label>
                <span className="hidden sm:inline normal-case tracking-normal">
                  Secure Connection
                </span>
              </div>
              <input
                type="password"
                id="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary w-full mt-5 sm:mt-6 touch-manipulation active:scale-[0.98]"
              disabled={loading}
            >
              {loading ? 'Connecting...' : 'Connect & Sync'}
            </button>
          </form>

          <div className="mt-6 sm:mt-8 rounded-xl border border-slate-800 bg-slate-950/70 p-3 sm:p-4 text-center text-xs text-slate-400">
            <p className="mb-1">Default credentials:</p>
            <p>
              <span className="text-slate-300">admin</span> /{' '}
              <span className="text-slate-300">changeme</span>
            </p>
          </div>

          <div className="mt-4 sm:mt-6 text-center text-[10px] sm:text-[11px] uppercase tracking-[0.3em] sm:tracking-[0.35em] text-slate-500">
            Desktop Client v1.0.0 - Status{' '}
            <span className="text-sky-400">Ready</span>
          </div>
        </div>
      </div>
    </div>
  );
}
