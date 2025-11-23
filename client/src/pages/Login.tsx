import { useState, type FormEvent } from 'react';
import logoMark from '../assets/baluhost-logo.svg';

interface LoginProps {
  onLogin: (user: any, token: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
        const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      // Handle empty or non-JSON responses
      const contentType = response.headers.get('content-type');
      let data: any = {};
      
      if (contentType && contentType.includes('application/json')) {
        try {
          data = await response.json();
        } catch (jsonError) {
          console.error('Failed to parse JSON response:', jsonError);
          throw new Error('Server returned invalid response');
        }
      } else {
        const text = await response.text();
        console.error('Non-JSON response:', text);
        throw new Error(`Server error: ${response.status}`);
      }

      if (!response.ok) {
        throw new Error(data.detail || data.error || `Login failed (${response.status})`);
      }

      const token: string | undefined = data.access_token ?? data.token;

      if (!token) {
        throw new Error('Login response did not include an access token');
      }

      onLogin(data.user, token);
    } catch (err: any) {
      console.error('Login error:', err);
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 text-slate-100">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 top-[-120px] h-[420px] w-[420px] rounded-full bg-sky-500/10 blur-3xl" />
        <div className="absolute right-[-120px] top-[18%] h-[460px] w-[460px] rounded-full bg-sky-500-secondary/10 blur-[140px]" />
        <div className="absolute left-[45%] bottom-[-180px] h-[340px] w-[340px] rounded-full bg-sky-500/5 blur-[120px]" />
      </div>

      <div className="relative z-10 w-full max-w-md px-6 sm:px-0">
        <div className="card border border-slate-800 bg-slate-900/55 p-10">
          <div className="flex flex-col items-center text-center">
            <div className="glow-ring h-16 w-16">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-slate-950 p-[2px] shadow-xl">
                <img src={logoMark} alt="BalùHost logo" className="h-full w-full rounded-full" />
              </div>
            </div>
            <h1 className="mt-6 text-3xl font-semibold tracking-wide text-slate-100">BalùHost</h1>
            <p className="mt-2 text-sm text-slate-100-tertiary">Secure Personal Cloud Gateway</p>
          </div>

          <form onSubmit={handleSubmit} className="mt-10 space-y-5">
            {error && (
              <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                {error}
              </div>
            )}

            <div className="space-y-2">
              <label htmlFor="username" className="text-xs font-medium uppercase tracking-[0.2em] text-slate-100-tertiary">
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
              <div className="flex items-center justify-between text-xs font-medium uppercase tracking-[0.2em] text-slate-100-tertiary">
                <label htmlFor="password">Password</label>
                <span className="text-slate-100-tertiary normal-case tracking-normal">Keep your vault secure</span>
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
              className="btn btn-primary w-full mt-6"
              disabled={loading}
            >
              {loading ? 'Authorising...' : 'Access System'}
            </button>
          </form>

          <div className="mt-8 rounded-xl border border-slate-800 bg-slate-950-secondary p-4 text-center text-xs text-slate-100-tertiary">
            Default credentials - <span className="text-slate-100-secondary">admin</span> / <span className="text-slate-100-secondary">changeme</span>
          </div>

          <div className="mt-6 text-center text-[11px] uppercase tracking-[0.35em] text-slate-100-tertiary">
            Firmware v4.2.0 - System Status <span className="text-sky-400">Optimal</span>
          </div>
        </div>
      </div>
    </div>
  );
}
