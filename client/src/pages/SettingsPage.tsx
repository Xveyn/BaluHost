import { useState, useEffect, lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { User, Lock, HardDrive, Clock, Download, Globe, Shield, ShieldCheck, ShieldOff, Copy, RefreshCw, KeyRound, GitBranch, Bell, Database, Layers } from 'lucide-react';
import ApiKeysTab from '../components/settings/ApiKeysTab';
import VCLTrackingPanel from '../components/vcl/VCLTrackingPanel';
import { apiClient } from '../lib/api';
import LanguageSettings from '../components/LanguageSettings';
import ByteUnitSettings from '../components/ByteUnitSettings';
import { formatBytes } from '../lib/formatters';
import { getStorageBreakdown } from '../api/system';
import type { StorageBreakdownResponse } from '../api/system';
import { getUserQuota } from '../api/vcl';
import { getCacheOverview } from '../api/ssd-file-cache';
import StorageBreakdownRing from '../components/settings/StorageBreakdownRing';
import type { QuotaInfo } from '../types/vcl';
import type { SSDCacheStats } from '../api/ssd-file-cache';
import { get2FAStatus, setup2FA, verifySetup2FA, disable2FA, regenerateBackupCodes, type TwoFactorStatus, type TwoFactorSetupData } from '../api/two-factor';

const NotificationPreferencesPage = lazy(() => import('./NotificationPreferencesPage'));

interface UserProfile {
  id: number;
  username: string;
  role: string;
  created_at: string;
}

interface StorageQuota {
  used_bytes: number;
  limit_bytes: number | null;
  available_bytes: number | null;
  percent_used: number | null;
}

interface Session {
  id: string;
  ip_address: string;
  user_agent: string;
  last_active: string;
  is_current: boolean;
}

function TwoFactorCard() {
  const { t } = useTranslation('settings');
  const [status, setStatus] = useState<TwoFactorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupData, setSetupData] = useState<TwoFactorSetupData | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [showDisable, setShowDisable] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const data = await get2FAStatus();
      setStatus(data);
    } catch {
      // Failed to load 2FA status
    } finally {
      setLoading(false);
    }
  };

  const handleStartSetup = async () => {
    setError('');
    setSaving(true);
    try {
      const data = await setup2FA();
      setSetupData(data);
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Failed to start 2FA setup');
    } finally {
      setSaving(false);
    }
  };

  const handleVerifySetup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!setupData) return;
    setError('');
    setSaving(true);
    try {
      const result = await verifySetup2FA(setupData.secret, verifyCode);
      setBackupCodes(result.backup_codes);
      setSetupData(null);
      setVerifyCode('');
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Invalid verification code');
    } finally {
      setSaving(false);
    }
  };

  const handleBackupCodesDone = () => {
    setBackupCodes(null);
    loadStatus();
  };

  const handleCopyBackupCodes = () => {
    if (backupCodes) {
      navigator.clipboard.writeText(backupCodes.join('\n'));
      toast.success(t('security.backupCodesCopied'));
    }
  };

  const handleDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await disable2FA(disablePassword, disableCode);
      setShowDisable(false);
      setDisablePassword('');
      setDisableCode('');
      loadStatus();
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Failed to disable 2FA');
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerateBackupCodes = async () => {
    if (!confirm(t('security.regenerateWarning'))) return;
    setError('');
    setSaving(true);
    try {
      const result = await regenerateBackupCodes();
      setBackupCodes(result.backup_codes);
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Failed to regenerate backup codes');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('security.twoFactor')}
        </h3>
        <p className="text-slate-400 text-sm">{t('profile.loading')}</p>
      </div>
    );
  }

  // Show backup codes after setup or regeneration
  if (backupCodes) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <KeyRound className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-amber-400" />
          {t('security.backupCodesTitle')}
        </h3>
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 mb-4">
          {t('security.backupCodesWarning')}
        </div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {backupCodes.map((code, i) => (
            <div key={i} className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/40 font-mono text-sm text-center">
              {code}
            </div>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <button
            onClick={handleCopyBackupCodes}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors touch-manipulation active:scale-95"
          >
            <Copy className="w-4 h-4" />
            {t('security.copyBackupCodes')}
          </button>
          <button
            onClick={handleBackupCodesDone}
            className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors touch-manipulation active:scale-95"
          >
            {t('security.backupCodesDone')}
          </button>
        </div>
      </div>
    );
  }

  // Show setup flow (QR code + verify)
  if (setupData) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('security.twoFactor')}
        </h3>

        {error && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
            {error}
          </div>
        )}

        <p className="text-sm text-slate-100-secondary mb-4">{t('security.setupStep1')}</p>

        <div className="flex justify-center mb-4">
          <img
            src={setupData.qr_code}
            alt="TOTP QR Code"
            className="w-48 h-48 sm:w-56 sm:h-56 rounded-lg bg-white p-2"
          />
        </div>

        <div className="mb-4">
          <label className="block text-xs font-medium text-slate-100-tertiary mb-1">{t('security.manualEntry')}</label>
          <div className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/40 font-mono text-sm break-all select-all">
            {setupData.secret}
          </div>
        </div>

        <p className="text-sm text-slate-100-secondary mb-3">{t('security.setupStep2')}</p>

        <form onSubmit={handleVerifySetup} className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">{t('security.verificationCode')}</label>
            <input
              type="text"
              value={verifyCode}
              onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              className="input text-center text-xl tracking-[0.4em] font-mono"
              placeholder="000000"
              autoComplete="one-time-code"
              inputMode="numeric"
              required
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => { setSetupData(null); setVerifyCode(''); setError(''); }}
              className="flex-1 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors touch-manipulation active:scale-95"
            >
              {t('security.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving || verifyCode.length < 6}
              className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
            >
              {saving ? t('security.verifying') : t('security.verify')}
            </button>
          </div>
        </form>
      </div>
    );
  }

  // Show disable form
  if (showDisable) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <ShieldOff className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-rose-400" />
          {t('security.disable2FA')}
        </h3>

        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
          {t('security.disableWarning')}
        </div>

        {error && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
            {error}
          </div>
        )}

        <form onSubmit={handleDisable} className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">{t('security.disablePassword')}</label>
            <input
              type="password"
              value={disablePassword}
              onChange={(e) => setDisablePassword(e.target.value)}
              className="input"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">{t('security.disableCode')}</label>
            <input
              type="text"
              value={disableCode}
              onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
              className="input text-center font-mono tracking-wider"
              placeholder="000000"
              autoComplete="one-time-code"
              inputMode="numeric"
              required
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => { setShowDisable(false); setError(''); setDisablePassword(''); setDisableCode(''); }}
              className="flex-1 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors touch-manipulation active:scale-95"
            >
              {t('security.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-rose-500 hover:bg-rose-600 transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
            >
              {saving ? t('security.changing') : t('security.disable2FA')}
            </button>
          </div>
        </form>
      </div>
    );
  }

  // Default: show status
  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
        <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
        {t('security.twoFactor')}
      </h3>
      <p className="text-sm text-slate-100-secondary mb-4">{t('security.twoFactorDescription')}</p>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
          {error}
        </div>
      )}

      {status?.enabled ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
            <ShieldCheck className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-emerald-300">{t('security.twoFactorEnabled')}</p>
              {status.enabled_at && (
                <p className="text-xs text-emerald-400/70">
                  {t('security.twoFactorEnabledSince')} {new Date(status.enabled_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 text-sm text-slate-100-secondary">
            <KeyRound className="w-4 h-4" />
            <span>{t('security.backupCodesRemaining', { count: status.backup_codes_remaining })}</span>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <button
              onClick={handleRegenerateBackupCodes}
              disabled={saving}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
            >
              <RefreshCw className="w-4 h-4" />
              {t('security.regenerateBackupCodes')}
            </button>
            <button
              onClick={() => { setShowDisable(true); setError(''); }}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-rose-300 rounded-lg bg-rose-500/10 border border-rose-500/30 hover:bg-rose-500/20 transition-colors touch-manipulation active:scale-95"
            >
              <ShieldOff className="w-4 h-4" />
              {t('security.disable2FA')}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/40">
            <ShieldOff className="w-5 h-5 text-slate-400 flex-shrink-0" />
            <p className="text-sm text-slate-400">{t('security.twoFactorDisabled')}</p>
          </div>
          <button
            onClick={handleStartSetup}
            disabled={saving}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
          >
            <ShieldCheck className="w-4 h-4" />
            {saving ? t('profile.loading') : t('security.enable2FA')}
          </button>
        </div>
      )}
    </div>
  );
}

function getUsageColor(percent: number): string {
  if (percent > 90) return '#ef4444';
  if (percent > 75) return '#f59e0b';
  return '#22c55e';
}

export default function SettingsPage() {
  const { t } = useTranslation('settings');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  type SettingsTab = 'profile' | 'security' | 'storage' | 'language' | 'api-keys' | 'vcl' | 'notifications';
  const validTabs: SettingsTab[] = ['profile', 'security', 'storage', 'language', 'api-keys', 'vcl', 'notifications'];
  const tabParam = searchParams.get('tab') as SettingsTab | null;
  const [activeTab, setActiveTab] = useState<SettingsTab>(
    tabParam && validTabs.includes(tabParam) ? tabParam : 'profile'
  );

  const handleTabChange = (tab: SettingsTab) => {
    setActiveTab(tab);
    setSearchParams(tab === 'profile' ? {} : { tab });
  };
  
  // Password change
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  // Storage quota
  const [storageQuota, setStorageQuota] = useState<StorageQuota | null>(null);
  const [storageBreakdown, setStorageBreakdown] = useState<StorageBreakdownResponse | null>(null);
  const [vclQuota, setVclQuota] = useState<QuotaInfo | null>(null);
  const [cacheOverview, setCacheOverview] = useState<SSDCacheStats[] | null>(null);

  // Sessions (mock data for now)
  const [sessions] = useState<Session[]>([
    {
      id: 'current',
      ip_address: '192.168.1.100',
      user_agent: 'Chrome 120 on Windows',
      last_active: new Date().toISOString(),
      is_current: true
    }
  ]);

  useEffect(() => {
    loadProfile();
    loadStorageQuota();
    loadStorageBreakdown();
    loadVclQuota();
    loadCacheOverview();
  }, []);

  const loadProfile = async () => {
    try {
      const response = await apiClient.get('/api/auth/me');

      // Backend returns user object directly, not wrapped in {user: ...}
      const userData = response.data;

      if (!userData || !userData.username) {
        throw new Error('No valid user data received');
      }

      setProfile(userData);
    } catch {
      // Failed to load profile
    } finally {
      setLoading(false);
    }
  };

  const loadStorageQuota = async () => {
    try {
      const response = await apiClient.get('/api/system/quota');
      setStorageQuota(response.data);
    } catch {
      // Failed to load storage quota
    }
  };

  const loadStorageBreakdown = async () => {
    try {
      const data = await getStorageBreakdown();
      setStorageBreakdown(data);
    } catch {
      // Failed to load storage breakdown
    }
  };

  const loadVclQuota = async () => {
    try {
      const data = await getUserQuota();
      setVclQuota(data);
    } catch {
      // VCL not available
    }
  };

  const loadCacheOverview = async () => {
    try {
      const data = await getCacheOverview();
      setCacheOverview(data);
    } catch {
      setCacheOverview([]);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match');
      return;
    }

    if (newPassword.length < 6) {
      toast.error('Password must be at least 6 characters');
      return;
    }
    
    setSaving(true);
    
    try {
      await apiClient.post('/api/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword
      });
      
      toast.success('Password changed successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(detail || 'Failed to change password');
    } finally {
      setSaving(false);
    }
  };

  const handleExportData = () => {
    toast('Data export feature coming soon!');
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };

  // Early returns for loading and error states
  if (loading || !profile) {
    return (
      <div className="text-center py-8 text-slate-400">
        {loading ? t('profile.loading') : t('profile.loadFailed')}
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('title')}</h1>
        <p className="mt-1 text-sm text-slate-400">{t('subtitle')}</p>
      </div>

      {/* Tabs */}
      <div className="relative">
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
          <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
            {([
              { id: 'profile' as const, label: t('tabs.profile'), icon: User },
              { id: 'security' as const, label: t('tabs.security'), icon: Lock },
              { id: 'storage' as const, label: t('tabs.storage'), icon: HardDrive },
              { id: 'vcl' as const, label: 'VCL', icon: GitBranch },
              { id: 'language' as const, label: t('tabs.language'), icon: Globe },
              { id: 'notifications' as const, label: t('tabs.notifications'), icon: Bell },
              ...(profile?.role === 'admin' ? [{ id: 'api-keys' as const, label: t('tabs.apiKeys'), icon: KeyRound }] : []),
            ]).map(tab => (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                  activeTab === tab.id
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                    : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
                }`}
              >
                <tab.icon className="w-4 h-4 sm:w-5 sm:h-5" />
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-950 to-transparent sm:hidden" />
      </div>

      <div className="w-full space-y-6">
        {/* Profile Tab */}
        {activeTab === 'profile' && (
          <>
            {/* Profile Card */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <div className="flex flex-col sm:flex-row items-center sm:items-start gap-4 sm:gap-6">
                <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-full flex-shrink-0 flex items-center justify-center text-white text-xl sm:text-2xl font-bold bg-gradient-to-br from-sky-500 to-violet-500">
                  {profile.username.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0 text-center sm:text-left">
                  <h2 className="text-xl sm:text-2xl font-bold truncate">{profile.username}</h2>
                  <p className="text-sm text-slate-100-secondary capitalize">{profile.role}</p>
                  <p className="text-sm text-slate-100-tertiary mt-1">
                    {t('profile.memberSince')} {new Date(profile.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>

              <div className="mt-6 pt-5 border-t border-slate-700/40">
                <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
                  <User className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
                  {t('profile.accountInfo')}
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="px-4 py-3 rounded-lg bg-slate-800/40 border border-slate-700/30">
                    <label className="block text-xs font-medium text-slate-100-tertiary mb-1">{t('profile.username')}</label>
                    <p className="text-sm sm:text-base font-medium truncate">{profile.username}</p>
                  </div>
                  <div className="px-4 py-3 rounded-lg bg-slate-800/40 border border-slate-700/30">
                    <label className="block text-xs font-medium text-slate-100-tertiary mb-1">{t('profile.role')}</label>
                    <p className="text-sm sm:text-base font-medium capitalize">{profile.role}</p>
                  </div>
                  <div className="px-4 py-3 rounded-lg bg-slate-800/40 border border-slate-700/30">
                    <label className="block text-xs font-medium text-slate-100-tertiary mb-1">{t('profile.accountId')}</label>
                    <p className="text-sm sm:text-base font-medium font-mono">{profile.id}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Data Export */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
                <Download className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
                {t('security.dataExport.title')}
              </h3>
              <p className="mb-3 sm:mb-4 text-sm sm:text-base text-slate-100-secondary">
                {t('security.dataExport.description')}
              </p>
              <button
                onClick={handleExportData}
                className="w-full sm:w-auto px-4 py-2 text-sm sm:text-base text-white rounded-lg transition-colors bg-sky-500 hover:bg-sky-500-secondary touch-manipulation active:scale-95"
              >
                {t('security.dataExport.button')}
              </button>
            </div>
          </>
        )}

        {/* Security Tab */}
        {activeTab === 'security' && (
          <>
            {/* Password Change */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
                <Lock className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
                {t('security.changePassword')}
              </h3>
              <form onSubmit={handleChangePassword} className="space-y-3 sm:space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">{t('security.currentPassword')}</label>
                  <input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="input"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">{t('security.newPassword')}</label>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="input"
                    required
                    minLength={6}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">{t('security.confirmPassword')}</label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="input"
                    required
                    minLength={6}
                  />
                </div>
                <button
                  type="submit"
                  disabled={saving}
                  className="w-full sm:w-auto px-4 py-2 text-sm sm:text-base text-white rounded-lg transition-colors disabled:opacity-50 bg-sky-500 hover:bg-sky-500-secondary touch-manipulation active:scale-95"
                >
                  {saving ? t('security.changing') : t('security.changePassword')}
                </button>
              </form>
            </div>

            {/* Two-Factor Authentication */}
            <TwoFactorCard />

            {/* Active Sessions */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
                <Clock className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
                {t('security.activeSessions')}
              </h3>
              <div className="space-y-3">
                {sessions.map(session => (
                  <div
                    key={session.id}
                    className="p-3 sm:p-4 rounded-lg border"
                    style={{
                      backgroundColor: 'var(--bg-secondary)',
                      borderColor: 'var(--border-primary)'
                    }}
                  >
                    <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm sm:text-base truncate">{session.user_agent}</p>
                        <p className="text-xs sm:text-sm text-slate-100-secondary">
                          IP: {session.ip_address}
                        </p>
                        <p className="text-xs sm:text-sm text-slate-100-tertiary">
                          {t('security.lastActive')}: {formatDate(session.last_active)}
                        </p>
                      </div>
                      {session.is_current && (
                        <span className="self-start px-2 py-1 text-xs rounded whitespace-nowrap" style={{ backgroundColor: 'var(--success)', color: 'white' }}>
                          {t('security.current')}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

          </>
        )}

        {/* Language Tab */}
        {activeTab === 'language' && (
          <>
            <LanguageSettings />
            <ByteUnitSettings />
          </>
        )}

        {/* API Keys Tab (Admin only) */}
        {activeTab === 'api-keys' && profile?.role === 'admin' && (
          <ApiKeysTab />
        )}

        {/* Storage Tab */}
        {activeTab === 'storage' && (
          <>
            {/* System Storage Overview */}
            <div className="card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(56,189,248,0.06)] hover:shadow-[0_8px_32px_rgba(56,189,248,0.12)] transition-shadow">
              <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
                <Database className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
                {t('storage.systemStorage')}
              </h3>
              {storageBreakdown ? (
                <div className="flex flex-col sm:flex-row items-center gap-6 sm:gap-8">
                  <StorageBreakdownRing
                    entries={storageBreakdown.entries}
                    totalCapacity={storageBreakdown.total_capacity}
                    totalUsePercent={storageBreakdown.total_use_percent}
                    size={140}
                    strokeWidth={12}
                  />
                  <div className="flex-1 space-y-3 w-full">
                    <div className="text-center sm:text-left">
                      <p className="text-xs text-slate-400 mb-0.5">{t('storage.totalCapacity')}</p>
                      <p className="text-2xl font-bold">{formatBytes(storageBreakdown.total_capacity)}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="px-3 py-2.5 rounded-lg bg-slate-800/40 border border-slate-700/30">
                        <p className="text-xs text-slate-400 mb-0.5">{t('storage.used')}</p>
                        <p className="text-sm font-semibold">{formatBytes(storageBreakdown.total_used)}</p>
                      </div>
                      <div className="px-3 py-2.5 rounded-lg bg-slate-800/40 border border-slate-700/30">
                        <p className="text-xs text-slate-400 mb-0.5">{t('storage.available')}</p>
                        <p className="text-sm font-semibold">{formatBytes(storageBreakdown.total_available)}</p>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col sm:flex-row items-center gap-6 animate-pulse">
                  <div className="w-[140px] h-[140px] rounded-full bg-slate-800/50" />
                  <div className="flex-1 space-y-3 w-full">
                    <div className="h-5 w-24 rounded bg-slate-700/50" />
                    <div className="h-8 w-32 rounded bg-slate-700/50" />
                    <div className="grid grid-cols-2 gap-3">
                      <div className="h-14 rounded-lg bg-slate-700/30" />
                      <div className="h-14 rounded-lg bg-slate-700/30" />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* My Arrays + VCL side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
              {/* My Arrays (renamed from Your Quota) — admin can click to RAID settings */}
              <div
                className={`card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(52,211,153,0.06)] hover:shadow-[0_8px_32px_rgba(52,211,153,0.12)] transition-all ${profile?.role === 'admin' ? 'cursor-pointer hover:border-emerald-500/30' : ''}`}
                {...(profile?.role === 'admin' ? { onClick: () => navigate('/admin/system-control?tab=raid') } : {})}
              >
                <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
                  <HardDrive className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-emerald-400" />
                  {t('storage.myArrays')}
                </h3>
                {storageQuota ? (
                  <div className="space-y-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-400">{t('storage.used')}</span>
                      <span className="font-semibold">
                        {formatBytes(storageQuota.used_bytes)}
                        {storageQuota.limit_bytes && ` / ${formatBytes(storageQuota.limit_bytes)}`}
                      </span>
                    </div>
                    {storageQuota.limit_bytes && storageQuota.percent_used != null ? (
                      <>
                        <div className="w-full h-3 rounded-full overflow-hidden bg-slate-800/60">
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{
                              width: `${Math.min(storageQuota.percent_used, 100)}%`,
                              backgroundColor: getUsageColor(storageQuota.percent_used)
                            }}
                          />
                        </div>
                        <p className="text-sm text-slate-400">
                          {formatBytes(storageQuota.available_bytes ?? 0)} {t('storage.remaining')}
                        </p>
                      </>
                    ) : (
                      <p className="text-sm text-slate-400">{t('storage.noLimit')}</p>
                    )}
                  </div>
                ) : (
                  <div className="space-y-3 animate-pulse">
                    <div className="flex justify-between">
                      <div className="h-4 w-16 rounded bg-slate-700/50" />
                      <div className="h-4 w-28 rounded bg-slate-700/50" />
                    </div>
                    <div className="w-full h-3 rounded-full bg-slate-700/50" />
                    <div className="h-3 w-24 rounded bg-slate-700/50" />
                  </div>
                )}
              </div>

              {/* VCL Storage Quota — clickable to switch to VCL tab */}
              <div
                className="card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(139,92,246,0.06)] hover:shadow-[0_8px_32px_rgba(139,92,246,0.12)] hover:border-violet-500/30 transition-all cursor-pointer"
                onClick={() => handleTabChange('vcl')}
                title={t('storage.vclClickHint')}
              >
                <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
                  <GitBranch className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-violet-400" />
                  {t('storage.vclTitle')}
                </h3>
                {vclQuota ? (
                  vclQuota.is_enabled ? (
                    <div className="space-y-3">
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-400">{t('storage.used')}</span>
                        <span className="font-semibold">
                          {formatBytes(vclQuota.current_usage_bytes)} / {formatBytes(vclQuota.max_size_bytes)}
                        </span>
                      </div>
                      <div className="w-full h-3 rounded-full overflow-hidden bg-slate-800/60">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{
                            width: `${Math.min(vclQuota.usage_percent, 100)}%`,
                            backgroundColor: getUsageColor(vclQuota.usage_percent)
                          }}
                        />
                      </div>
                      <p className="text-sm text-slate-400">
                        {formatBytes(vclQuota.available_bytes)} {t('storage.remaining')}
                      </p>
                      <div className="grid grid-cols-3 gap-2 pt-3 border-t border-slate-700/40">
                        <div className="text-center px-2 py-1.5 rounded-lg bg-slate-800/40">
                          <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.compression')}</p>
                          <p className={`text-xs font-medium mt-0.5 ${vclQuota.compression_enabled ? 'text-emerald-400' : 'text-slate-500'}`}>
                            {vclQuota.compression_enabled ? t('storage.enabled') : t('storage.disabled')}
                          </p>
                        </div>
                        <div className="text-center px-2 py-1.5 rounded-lg bg-slate-800/40">
                          <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.deduplication')}</p>
                          <p className={`text-xs font-medium mt-0.5 ${vclQuota.dedupe_enabled ? 'text-emerald-400' : 'text-slate-500'}`}>
                            {vclQuota.dedupe_enabled ? t('storage.enabled') : t('storage.disabled')}
                          </p>
                        </div>
                        <div className="text-center px-2 py-1.5 rounded-lg bg-slate-800/40">
                          <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.depth')}</p>
                          <p className="text-xs font-medium mt-0.5">{vclQuota.depth}</p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/40">
                      <GitBranch className="w-5 h-5 text-slate-500" />
                      <p className="text-sm text-slate-400">{t('storage.vclDisabled')}</p>
                    </div>
                  )
                ) : (
                  <div className="space-y-3 animate-pulse">
                    <div className="flex justify-between">
                      <div className="h-4 w-16 rounded bg-slate-700/50" />
                      <div className="h-4 w-28 rounded bg-slate-700/50" />
                    </div>
                    <div className="w-full h-3 rounded-full bg-slate-700/50" />
                    <div className="h-3 w-24 rounded bg-slate-700/50" />
                  </div>
                )}
              </div>
            </div>

            {/* SSD Cache */}
            <div className="card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(245,158,11,0.06)] hover:shadow-[0_8px_32px_rgba(245,158,11,0.12)] transition-shadow">
              <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
                <Layers className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-amber-400" />
                {t('storage.cacheTitle')}
              </h3>
              {cacheOverview === null ? (
                <div className="space-y-3 animate-pulse">
                  <div className="h-20 rounded-lg bg-slate-700/30" />
                </div>
              ) : cacheOverview.length === 0 ? (
                <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/40">
                  <Layers className="w-5 h-5 text-slate-500" />
                  <p className="text-sm text-slate-400">{t('storage.noCacheConfigured')}</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {cacheOverview.map(cache => (
                    <div key={cache.array_name} className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/30">
                      <div className="flex justify-between items-center mb-3">
                        <span className="font-medium text-sm">{t('storage.cacheFor', { array: cache.array_name })}</span>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                          cache.is_enabled
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                            : 'bg-slate-700/50 text-slate-400 border border-slate-600/30'
                        }`}>
                          {cache.is_enabled ? t('storage.enabled') : t('storage.disabled')}
                        </span>
                      </div>
                      {cache.ssd_total_bytes > 0 && (
                        <p className="text-xs text-slate-500 mb-2">
                          SSD {formatBytes(cache.ssd_total_bytes)} — {formatBytes(cache.ssd_available_bytes)} {t('storage.available').toLowerCase()}
                        </p>
                      )}
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-slate-400">{t('storage.used')}</span>
                        <span className="font-semibold">
                          {formatBytes(cache.current_size_bytes)} / {formatBytes(cache.max_size_bytes)}
                        </span>
                      </div>
                      <div className="w-full h-2.5 rounded-full overflow-hidden bg-slate-800/60 mb-4">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{
                            width: `${Math.min(cache.usage_percent, 100)}%`,
                            backgroundColor: '#f59e0b'
                          }}
                        />
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div className="text-center p-2 rounded-lg bg-slate-900/60">
                          <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.hitRate')}</p>
                          <p className="text-sm font-semibold text-amber-400 mt-0.5">
                            {cache.hit_rate_percent.toFixed(1)}%
                          </p>
                        </div>
                        <div className="text-center p-2 rounded-lg bg-slate-900/60">
                          <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.entries')}</p>
                          <p className="text-sm font-semibold mt-0.5">
                            {cache.valid_entries} / {cache.total_entries}
                          </p>
                        </div>
                        <div className="text-center p-2 rounded-lg bg-slate-900/60">
                          <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.served')}</p>
                          <p className="text-sm font-semibold mt-0.5">
                            {formatBytes(cache.total_bytes_served)}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {activeTab === 'vcl' && <VCLTrackingPanel />}

        {/* Notifications Tab */}
        {activeTab === 'notifications' && (
          <Suspense fallback={<div className="text-center py-8 text-slate-400">{t('profile.loading')}</div>}>
            <NotificationPreferencesPage embedded />
          </Suspense>
        )}

      </div>
    </div>
  );
}
