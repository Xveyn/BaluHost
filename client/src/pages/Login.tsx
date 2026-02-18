import { useState, useEffect, useRef, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { User } from '../types/auth';
import logoMark from '../assets/baluhost-logo.png';
import { localApi } from '../lib/localApi';
import { useVersion } from '../contexts/VersionContext';
import { DeveloperBadge } from '../components/ui/DeveloperBadge';
import { useAuth } from '../contexts/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const { t } = useTranslation('login');
  const { version, loading: versionLoading } = useVersion();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [localBackendAvailable, setLocalBackendAvailable] = useState(false);
  const [connectionMode, setConnectionMode] = useState<'checking' | 'local' | 'ipc' | 'fallback'>('checking');
  const [isDevMode, setIsDevMode] = useState(false);

  // 2FA state
  const [twoFactorRequired, setTwoFactorRequired] = useState(false);
  const [pendingToken, setPendingToken] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const totpInputRef = useRef<HTMLInputElement>(null);

  // Check if local backend is available on component mount
  useEffect(() => {
    const checkBackend = async () => {
      const available = await localApi.isAvailable();
      setLocalBackendAvailable(available);
      setConnectionMode(available ? 'local' : 'ipc');
    };
    checkBackend();
  }, []);

  // Check if running in dev mode (for showing default credentials)
  useEffect(() => {
    fetch('/api/system/mode')
      .then(res => res.json())
      .then(data => setIsDevMode(data.dev_mode === true))
      .catch(() => setIsDevMode(false));
  }, []);

  // Focus TOTP input when 2FA step is shown
  useEffect(() => {
    if (twoFactorRequired && totpInputRef.current) {
      totpInputRef.current.focus();
    }
  }, [twoFactorRequired]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      // Strategy 1: Try local API if available
      if (localBackendAvailable) {
        try {
          const loginResult = await localApi.login(username, password);

          // Check if 2FA is required - login may return a different shape
          const resultObj = loginResult as unknown as Record<string, unknown>;
          if (resultObj.requires_2fa) {
            setPendingToken(String(resultObj.pending_token ?? ''));
            setTwoFactorRequired(true);
            setLoading(false);
            return;
          }

          setConnectionMode('local');
          login(loginResult.user, loginResult.access_token);
          return;
        } catch (localErr: unknown) {
          setConnectionMode('fallback');
          // Continue to fallback strategy
        }
      }

      // Strategy 2: Fall back to regular fetch (via proxy or IPC)
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      // Handle empty or non-JSON responses
      const contentType = response.headers.get('content-type');
      let data: Record<string, unknown> = {};

      if (contentType && contentType.includes('application/json')) {
        try {
          data = await response.json();
        } catch {
          throw new Error('Server returned invalid response');
        }
      } else {
        await response.text();
        throw new Error(`Server error: ${response.status}`);
      }

      if (!response.ok) {
        throw new Error(String(data.detail || data.error || `Login failed (${response.status})`));
      }

      // Check if 2FA is required
      if (data.requires_2fa) {
        setPendingToken(String(data.pending_token ?? ''));
        setTwoFactorRequired(true);
        setLoading(false);
        return;
      }

      const token = data.access_token ?? data.token;

      if (typeof token !== 'string') {
        throw new Error('Login response did not include an access token');
      }

      login(data.user as User, token);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify2FA = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await fetch('/api/auth/verify-2fa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pending_token: pendingToken, code: totpCode }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || t('twoFactor.invalidCode'));
      }

      const token: string | undefined = data.access_token ?? data.token;
      if (!token) {
        throw new Error('Response did not include an access token');
      }

      // Store token
      localStorage.setItem('token', token);
      login(data.user, token);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('twoFactor.invalidCode'));
      setTotpCode('');
    } finally {
      setLoading(false);
    }
  };

  const handleBackToLogin = () => {
    setTwoFactorRequired(false);
    setPendingToken('');
    setTotpCode('');
    setError('');
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden text-slate-100">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 top-[-120px] h-[420px] w-[420px] rounded-full bg-sky-500/10 blur-3xl" />
        <div className="absolute right-[-120px] top-[18%] h-[460px] w-[460px] rounded-full bg-sky-500-secondary/10 blur-[140px]" />
        <div className="absolute left-[45%] bottom-[-180px] h-[340px] w-[340px] rounded-full bg-sky-500/5 blur-[120px]" />
      </div>

      <div className="relative z-10 w-full max-w-md px-4 sm:px-6">
        <div className="card border border-slate-800 bg-slate-900/55 p-6 sm:p-10">
          <div className="flex flex-col items-center text-center">
            <div className="glow-ring h-14 w-14 sm:h-16 sm:w-16">
              <div className="flex h-12 w-12 sm:h-14 sm:w-14 items-center justify-center rounded-full bg-slate-950 p-[2px] shadow-xl">
                <img src={logoMark} alt="BalùHost logo" className="h-full w-full rounded-full" />
              </div>
            </div>
            <h1 className="mt-5 sm:mt-6 text-2xl sm:text-3xl font-semibold tracking-wide text-slate-100">{t('title')}</h1>
            <p className="mt-2 text-sm text-slate-100-tertiary">{twoFactorRequired ? t('twoFactor.subtitle') : t('subtitle')}</p>

            {/* Developer Build Badge */}
            <DeveloperBadge size="md" className="mt-3" />

            {/* Connection mode indicator */}
            {connectionMode !== 'checking' && (
              <div className="mt-3 flex items-center gap-2 text-xs">
                <div className={`h-2 w-2 rounded-full ${
                  connectionMode === 'local' ? 'bg-emerald-400 animate-pulse' :
                  connectionMode === 'ipc' ? 'bg-amber-400' :
                  'bg-slate-400'
                }`} />
                <span className="text-slate-100-tertiary uppercase tracking-wider">
                  {connectionMode === 'local' ? t('connectionModes.local') :
                   connectionMode === 'ipc' ? t('connectionModes.network') :
                   t('connectionModes.fallback')}
                </span>
              </div>
            )}
          </div>

          {/* 2FA Verification Step */}
          {twoFactorRequired ? (
            <form onSubmit={handleVerify2FA} className="mt-8 sm:mt-10 space-y-4 sm:space-y-5">
{error && (
                <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 sm:px-4 py-2.5 sm:py-3 text-sm text-rose-200">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <label htmlFor="totp-code" className="text-xs font-medium uppercase tracking-[0.2em] text-slate-100-tertiary">
                  {t('twoFactor.codeLabel')}
                </label>
                <input
                  ref={totpInputRef}
                  type="text"
                  id="totp-code"
                  className="input text-center text-2xl tracking-[0.5em] font-mono"
                  value={totpCode}
                  onChange={(e) => {
                    const val = e.target.value.replace(/\D/g, '').slice(0, 8);
                    setTotpCode(val);
                  }}
                  placeholder={t('twoFactor.codePlaceholder')}
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  required
                />
                <p className="text-xs text-slate-100-tertiary text-center mt-1">
                  {t('twoFactor.useBackupCode')}
                </p>
              </div>

              <button
                type="submit"
                className="btn btn-primary w-full mt-5 sm:mt-6 touch-manipulation active:scale-[0.98]"
                disabled={loading || totpCode.length < 6}
              >
                {loading ? t('twoFactor.verifying') : t('twoFactor.verify')}
              </button>

              <button
                type="button"
                onClick={handleBackToLogin}
                className="w-full text-center text-sm text-slate-100-tertiary hover:text-slate-100-secondary transition-colors"
              >
                {t('twoFactor.backToLogin')}
              </button>
            </form>
          ) : (
            /* Regular Login Form */
            <>
              <form onSubmit={handleSubmit} className="mt-8 sm:mt-10 space-y-4 sm:space-y-5">
                {error && (
                  <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 sm:px-4 py-2.5 sm:py-3 text-sm text-rose-200">
                    {error}
                  </div>
                )}

                <div className="space-y-2">
                  <label htmlFor="username" className="text-xs font-medium uppercase tracking-[0.2em] text-slate-100-tertiary">
                    {t('form.username')}
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
                    <label htmlFor="password">{t('form.password')}</label>
                    <span className="hidden sm:inline text-slate-100-tertiary normal-case tracking-normal">{t('form.passwordHint')}</span>
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
                  {loading ? t('form.loading') : t('form.submit')}
                </button>
              </form>

              {isDevMode && (
                <div className="mt-6 sm:mt-8 rounded-xl border border-slate-800 bg-slate-950-secondary p-3 sm:p-4 text-center text-xs text-slate-100-tertiary">
                  {t('defaultCredentials')} - <span className="text-slate-100-secondary">admin</span> / <span className="text-slate-100-secondary">changeme</span>
                </div>
              )}
            </>
          )}

          <div className="mt-4 sm:mt-6 text-center text-[10px] sm:text-[11px] uppercase tracking-[0.3em] sm:tracking-[0.35em] text-slate-100-tertiary">
            {t('firmware')} v{versionLoading ? '...' : (version || '?.?.?')}{__BUILD_TYPE__ === 'dev' && <span className="font-mono"> · {__GIT_COMMIT__}</span>} - {t('systemStatus')} <span className="text-sky-400">{t('optimal')}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
