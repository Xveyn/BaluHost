import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { User, Lock, Mail, Image, HardDrive, Clock, Download, Globe, Shield, ShieldCheck, ShieldOff, Copy, RefreshCw, KeyRound } from 'lucide-react';
import { apiClient } from '../lib/api';
import LanguageSettings from '../components/LanguageSettings';
import { formatBytes } from '../lib/formatters';
import { get2FAStatus, setup2FA, verifySetup2FA, disable2FA, regenerateBackupCodes, type TwoFactorStatus, type TwoFactorSetupData } from '../api/two-factor';

interface UserProfile {
  id: number;
  username: string;
  email: string | null;
  role: string;
  avatar_url: string | null;
  created_at: string;
}

interface StorageQuota {
  used_bytes: number;
  quota_bytes: number | null;
  percentage: number;
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
      alert(t('security.backupCodesCopied'));
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

export default function SettingsPage() {
  const { t } = useTranslation('settings');
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'profile' | 'security' | 'storage' | 'language'>('profile');
  
  // Profile update
  const [email, setEmail] = useState('');
  
  // Password change
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  // Avatar upload
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);

  // Storage quota
  const [storageQuota, setStorageQuota] = useState<StorageQuota | null>(null);

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
      setEmail(userData.email || '');
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

  const handleUpdateEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    
    try {
      await apiClient.patch(`/api/users/${profile?.id}`, { email });
      alert('Email updated successfully');
      await loadProfile();
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      alert(detail || 'Failed to update email');
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (newPassword !== confirmPassword) {
      alert('New passwords do not match');
      return;
    }
    
    if (newPassword.length < 6) {
      alert('Password must be at least 6 characters');
      return;
    }
    
    setSaving(true);
    
    try {
      await apiClient.post('/api/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword
      });
      
      alert('Password changed successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      alert(detail || 'Failed to change password');
    } finally {
      setSaving(false);
    }
  };

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setAvatarFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setAvatarPreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleAvatarUpload = async () => {
    if (!avatarFile) return;
    
    setSaving(true);
    const formData = new FormData();
    formData.append('avatar', avatarFile);
    
    try {
      await apiClient.post(`/api/users/${profile?.id}/avatar`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      alert('Avatar updated successfully');
      setAvatarFile(null);
      setAvatarPreview(null);
      await loadProfile();
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      alert(detail || 'Failed to upload avatar');
    } finally {
      setSaving(false);
    }
  };

  const handleExportData = () => {
    alert('Data export feature coming soon!');
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
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
        <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
          {([
            { id: 'profile' as const, label: t('tabs.profile'), icon: User },
            { id: 'security' as const, label: t('tabs.security'), icon: Lock },
            { id: 'storage' as const, label: t('tabs.storage'), icon: HardDrive },
            { id: 'language' as const, label: t('tabs.language'), icon: Globe },
          ]).map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
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

      <div className="w-full space-y-6">
        {/* Profile Tab */}
        {activeTab === 'profile' && (
          <>
            {/* Profile Card */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <div className="flex flex-col sm:flex-row items-center sm:space-x-4 mb-4 sm:mb-6">
                <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-full flex items-center justify-center text-white text-xl sm:text-2xl font-bold bg-gradient-to-br from-sky-500 to-violet-500 mb-3 sm:mb-0">
                  {profile.avatar_url ? (
                    <img
                      src={profile.avatar_url}
                      alt={profile.username}
                      className="w-full h-full rounded-full object-cover"
                    />
                  ) : (
                    profile.username.charAt(0).toUpperCase()
                  )}
                </div>
                <div>
                  <h2 className="text-2xl font-bold">{profile.username}</h2>
                  <p className="text-slate-100-secondary">{profile.role}</p>
                  <p className="text-sm text-slate-100-tertiary">
                    {t('profile.memberSince')} {new Date(profile.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
            </div>

            {/* Avatar Upload */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-lg font-semibold mb-4 flex items-center">
                <Image className="w-5 h-5 mr-2 text-sky-400" />
                {t('profile.avatar')}
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">{t('profile.uploadAvatar')}</label>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleAvatarChange}
                    className="block w-full text-sm rounded-lg border border-slate-800 bg-slate-950-secondary text-slate-100-secondary px-3 py-2"
                  />
                </div>
                {avatarPreview && (
                  <div>
                    <p className="text-sm mb-2 text-slate-100-secondary">{t('profile.preview')}:</p>
                    <img
                      src={avatarPreview}
                      alt="Avatar preview"
                      className="w-24 h-24 sm:w-32 sm:h-32 rounded-full object-cover"
                    />
                    <button
                      onClick={handleAvatarUpload}
                      disabled={saving}
                      className="mt-4 px-4 py-2 text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50"
                    >
                      {saving ? t('profile.uploading') : t('profile.uploadAvatarBtn')}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Email Update */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
                <Mail className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
                {t('profile.email')}
              </h3>
              <form onSubmit={handleUpdateEmail} className="space-y-3 sm:space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">{t('profile.emailLabel')}</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="input"
                    placeholder="your.email@example.com"
                  />
                </div>
                <button
                  type="submit"
                  disabled={saving}
                  className="w-full sm:w-auto px-4 py-2 text-sm sm:text-base text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
                >
                  {saving ? t('profile.saving') : t('profile.updateEmail')}
                </button>
              </form>
            </div>

            {/* Account Info */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
                <User className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
                {t('profile.accountInfo')}
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-slate-100-secondary">{t('profile.username')}</label>
                  <p className="text-base sm:text-lg truncate">{profile.username}</p>
                </div>
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-slate-100-secondary">{t('profile.role')}</label>
                  <p className="text-base sm:text-lg capitalize">{profile.role}</p>
                </div>
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-slate-100-secondary">{t('profile.accountId')}</label>
                  <p className="text-base sm:text-lg font-mono">{profile.id}</p>
                </div>
              </div>
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

        {/* Language Tab */}
        {activeTab === 'language' && (
          <LanguageSettings />
        )}

        {/* Storage Tab */}
        {activeTab === 'storage' && (
          <>
            {/* Storage Quota */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
                <HardDrive className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
                {t('storage.title')}
              </h3>
              {storageQuota ? (
                <>
                  <div className="mb-4">
                    <div className="flex justify-between mb-2">
                      <span className="text-slate-100-secondary">{t('storage.used')}</span>
                      <span className="font-semibold">
                        {formatBytes(storageQuota.used_bytes)}
                        {storageQuota.quota_bytes && ` / ${formatBytes(storageQuota.quota_bytes)}`}
                      </span>
                    </div>
                    {storageQuota.quota_bytes && (
                      <div className="w-full h-4 rounded-full overflow-hidden bg-slate-950-tertiary">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.min(storageQuota.percentage, 100)}%`,
                            backgroundColor: storageQuota.percentage > 90 ? 'var(--error)' :
                                           storageQuota.percentage > 75 ? 'var(--warning)' :
                                           'var(--success)'
                          }}
                        />
                      </div>
                    )}
                  </div>
                  {storageQuota.quota_bytes && (
                    <p className="text-sm text-slate-100-tertiary">
                      {formatBytes(storageQuota.quota_bytes - storageQuota.used_bytes)} {t('storage.remaining')}
                    </p>
                  )}
                  {!storageQuota.quota_bytes && (
                    <p className="text-sm text-slate-100-tertiary">
                      {t('storage.noLimit')}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-slate-100-secondary">{t('storage.loading')}</p>
              )}
            </div>

            {/* Storage Info */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4">{t('storage.tipsTitle')}</h3>
              <ul className="space-y-2 text-sm sm:text-base text-slate-100-secondary">
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>{t('storage.tips.deleteFiles')}</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>{t('storage.tips.compression')}</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>{t('storage.tips.contactAdmin')}</span>
                </li>
              </ul>
            </div>
          </>
        )}

      </div>
    </div>
  );
}
