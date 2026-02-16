import { useState, useEffect } from 'react';
import { X, ArrowRight, Loader2, KeyRound, Info, Settings, ExternalLink } from 'lucide-react';
import {
  getOAuthUrl,
  getProviders,
  connectICloud,
  submitICloud2FA,
  createDevConnection,
  setOAuthConfig,
  extractErrorMessage,
  type CloudProvider,
  type CloudConnection,
  type ProvidersStatus,
  PROVIDER_LABELS,
} from '../../api/cloud-import';
import { toast } from 'react-hot-toast';

const PROVIDERS: { id: CloudProvider; gradient: string; icon: string }[] = [
  { id: 'google_drive', gradient: 'from-blue-500 to-green-500', icon: 'GD' },
  { id: 'onedrive', gradient: 'from-blue-600 to-sky-400', icon: 'OD' },
  { id: 'icloud', gradient: 'from-slate-400 to-slate-200', icon: 'iC' },
];

const PROVIDER_HELP: Record<string, { label: string; hint: string }> = {
  google_drive: {
    label: 'Google Drive',
    hint: 'Create credentials in the Google Cloud Console under APIs & Services > Credentials.',
  },
  onedrive: {
    label: 'OneDrive',
    hint: 'Register an app in the Azure Portal under App registrations.',
  },
};

interface CloudConnectWizardProps {
  onClose: () => void;
  onConnected: (conn: CloudConnection) => void;
}

export function CloudConnectWizard({ onClose, onConnected }: CloudConnectWizardProps) {
  const [step, setStep] = useState<'provider' | 'configure' | 'icloud-login' | 'icloud-2fa'>('provider');
  const [loading, setLoading] = useState(false);
  const [providerStatus, setProviderStatus] = useState<ProvidersStatus | null>(null);

  // Configure step fields
  const [configProvider, setConfigProvider] = useState<CloudProvider | null>(null);
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');

  // iCloud fields
  const [appleId, setAppleId] = useState('');
  const [password, setPassword] = useState('');
  const [pendingConnection, setPendingConnection] = useState<CloudConnection | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');

  const loadProviders = () => {
    getProviders()
      .then(setProviderStatus)
      .catch(() => {});
  };

  // Load provider availability on mount
  useEffect(() => {
    loadProviders();
  }, []);

  const isDevMode = providerStatus?.is_dev_mode ?? false;

  const handleSelectProvider = async (provider: CloudProvider) => {
    const info = providerStatus?.providers[provider];

    if (isDevMode) {
      // Dev mode: create mock connection immediately
      setLoading(true);
      try {
        const conn = await createDevConnection(provider);
        toast.success(`Connected to ${PROVIDER_LABELS[provider]} (Dev)`);
        onConnected(conn);
        onClose();
      } catch (err: unknown) {
        toast.error(extractErrorMessage(err, 'Connection failed'));
      } finally {
        setLoading(false);
      }
      return;
    }

    // Unconfigured OAuth provider — user can configure their own credentials
    if (info && !info.configured && info.auth_type === 'oauth') {
      setConfigProvider(provider);
      setClientId('');
      setClientSecret('');
      setStep('configure');
      return;
    }

    if (provider === 'icloud') {
      setStep('icloud-login');
      return;
    }

    // OAuth providers: redirect to OAuth URL
    setLoading(true);
    try {
      const url = await getOAuthUrl(provider);
      window.location.href = url;
    } catch (err: unknown) {
      toast.error(extractErrorMessage(err, 'Failed to start OAuth'));
      setLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    if (!configProvider || !clientId || !clientSecret) return;

    setLoading(true);
    try {
      await setOAuthConfig(configProvider, clientId, clientSecret);
      toast.success(`${PROVIDER_LABELS[configProvider]} configured successfully`);
      loadProviders();
      setStep('provider');
    } catch (err: unknown) {
      toast.error(extractErrorMessage(err, 'Failed to save credentials'));
    } finally {
      setLoading(false);
    }
  };

  const handleICloudLogin = async () => {
    if (!appleId || !password) return;

    setLoading(true);
    try {
      const result = await connectICloud(appleId, password);
      if (result.requires_2fa) {
        setPendingConnection(result.connection);
        setStep('icloud-2fa');
      } else {
        toast.success('Connected to iCloud');
        onConnected(result.connection);
        onClose();
      }
    } catch (err: unknown) {
      toast.error(extractErrorMessage(err, 'iCloud login failed'));
    } finally {
      setLoading(false);
    }
  };

  const handleICloud2FA = async () => {
    if (!pendingConnection || !twoFactorCode) return;

    setLoading(true);
    try {
      await submitICloud2FA(pendingConnection.id, twoFactorCode);
      toast.success('Connected to iCloud');
      onConnected(pendingConnection);
      onClose();
    } catch (err: unknown) {
      toast.error(extractErrorMessage(err, 'Invalid 2FA code'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-slate-700/50 bg-slate-900 p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-100">
            {step === 'provider' && 'Connect Cloud Storage'}
            {step === 'configure' && configProvider && `Configure ${PROVIDER_LABELS[configProvider]}`}
            {step === 'icloud-login' && 'iCloud Login'}
            {step === 'icloud-2fa' && 'Two-Factor Authentication'}
          </h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Step: Provider selection */}
        {step === 'provider' && (
          <div className="space-y-3">
            {isDevMode && (
              <p className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-400">
                Dev mode: Connections use mock data, no real credentials needed.
              </p>
            )}
            {PROVIDERS.map((p) => {
              const info = providerStatus?.providers[p.id];
              const isConfigured = isDevMode || !info || info.configured;
              const isOAuth = info?.auth_type === 'oauth';
              const authHint = isOAuth ? 'OAuth' : 'Credentials';

              return (
                <button
                  key={p.id}
                  onClick={() => handleSelectProvider(p.id)}
                  disabled={loading}
                  className="flex w-full items-center gap-4 rounded-xl border border-slate-700/50 bg-slate-800/40 p-4 text-left transition-all hover:border-slate-600/50 hover:bg-slate-800/60 disabled:opacity-50"
                >
                  <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br ${p.gradient} text-sm font-bold text-white`}>
                    {p.icon}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-slate-200">{PROVIDER_LABELS[p.id]}</p>
                    {!isDevMode && !isConfigured && isOAuth ? (
                      <p className="flex items-center gap-1 text-xs text-sky-400/80">
                        <Settings className="h-3 w-3" />
                        Click to configure
                      </p>
                    ) : (
                      <p className="text-xs text-slate-500">
                        {isDevMode ? 'Mock connection' : `Connect via ${authHint}`}
                      </p>
                    )}
                  </div>
                  {!isDevMode && !isConfigured && isOAuth ? (
                    <Settings className="h-4 w-4 text-sky-500/60" />
                  ) : (
                    <ArrowRight className="h-4 w-4 text-slate-600" />
                  )}
                </button>
              );
            })}

            {/* Hint for unconfigured providers */}
            {!isDevMode && providerStatus && Object.values(providerStatus.providers).some(p => !p.configured) && (
              <div className="mt-2 flex items-start gap-2 rounded-lg border border-slate-700/30 bg-slate-800/20 px-3 py-2">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
                <p className="text-xs text-slate-500">
                  Enter your own OAuth credentials to connect unconfigured providers.
                </p>
              </div>
            )}

            {loading && (
              <div className="flex items-center justify-center gap-2 py-4 text-slate-500">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Connecting...</span>
              </div>
            )}
          </div>
        )}

        {/* Step: Configure OAuth credentials */}
        {step === 'configure' && configProvider && (
          <div className="space-y-4">
            <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 px-3 py-2">
              <p className="text-xs text-sky-400">
                <ExternalLink className="mr-1 inline h-3 w-3" />
                {PROVIDER_HELP[configProvider]?.hint}
              </p>
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-400">Client ID</label>
              <input
                type="text"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="e.g. 123456789.apps.googleusercontent.com"
                className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-sky-500/50"
                autoFocus
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-400">Client Secret</label>
              <input
                type="password"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                placeholder="Client Secret"
                className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-sky-500/50"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setStep('provider')}
                className="rounded-lg border border-slate-700/50 px-4 py-2 text-sm text-slate-400 hover:bg-slate-800"
              >
                Back
              </button>
              <button
                onClick={handleSaveConfig}
                disabled={loading || !clientId || !clientSecret}
                className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <KeyRound className="h-4 w-4" />
                )}
                Save
              </button>
            </div>
          </div>
        )}

        {/* Step: iCloud login */}
        {step === 'icloud-login' && (
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-400">Apple ID</label>
              <input
                type="email"
                value={appleId}
                onChange={(e) => setAppleId(e.target.value)}
                placeholder="user@icloud.com"
                className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-sky-500/50"
                autoFocus
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-400">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password or App-Specific Password"
                className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-sky-500/50"
              />
              <p className="mt-1 text-xs text-slate-600">
                We recommend using an App-Specific Password from appleid.apple.com
              </p>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setStep('provider')}
                className="rounded-lg border border-slate-700/50 px-4 py-2 text-sm text-slate-400 hover:bg-slate-800"
              >
                Back
              </button>
              <button
                onClick={handleICloudLogin}
                disabled={loading || !appleId || !password}
                className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <KeyRound className="h-4 w-4" />
                )}
                Connect
              </button>
            </div>
          </div>
        )}

        {/* Step: iCloud 2FA */}
        {step === 'icloud-2fa' && (
          <div className="space-y-4">
            <p className="text-sm text-slate-400">
              Enter the 6-digit verification code sent to your trusted device.
            </p>
            <input
              type="text"
              value={twoFactorCode}
              onChange={(e) => setTwoFactorCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
              maxLength={6}
              className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-3 text-center text-2xl tracking-[0.5em] text-slate-200 outline-none placeholder:text-slate-700 focus:border-sky-500/50"
              autoFocus
            />
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={onClose}
                className="rounded-lg border border-slate-700/50 px-4 py-2 text-sm text-slate-400 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={handleICloud2FA}
                disabled={loading || twoFactorCode.length !== 6}
                className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <KeyRound className="h-4 w-4" />
                )}
                Verify
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
