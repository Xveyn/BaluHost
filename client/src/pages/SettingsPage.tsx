import { useState, useEffect, lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { User, Lock, Clock, Download, Globe, KeyRound, GitBranch, Bell, HardDrive } from 'lucide-react';
import ApiKeysTab from '../components/settings/ApiKeysTab';
import TwoFactorCard from '../components/settings/TwoFactorCard';
import VCLTrackingPanel from '../components/vcl/VCLTrackingPanel';
import { apiClient } from '../lib/api';
import LanguageSettings from '../components/LanguageSettings';
import ByteUnitSettings from '../components/ByteUnitSettings';
import StorageTab from '../components/settings/StorageTab';

const NotificationPreferencesPage = lazy(() => import('./NotificationPreferencesPage'));

interface UserProfile {
  id: number;
  username: string;
  role: string;
  created_at: string;
}

export default function SettingsPage() {
  const { t } = useTranslation('settings');
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
  
  // Sessions (mock data for now)
  interface SessionInfo { id: string; ip_address: string; user_agent: string; last_active: string; is_current: boolean; }
  const [sessions] = useState<SessionInfo[]>([
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
          <StorageTab
            isAdmin={profile?.role === 'admin'}
            onNavigateToVcl={() => handleTabChange('vcl')}
          />
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
