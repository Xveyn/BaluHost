import { useState, useEffect } from 'react';
import { User, Lock, Mail, Image, HardDrive, Clock, Activity, Download, Database } from 'lucide-react';
import { apiClient } from '../lib/api';
import BackupSettings from '../components/BackupSettings';

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

interface AuditLog {
  id: number;
  action: string;
  timestamp: string;
  details: Record<string, any>;
  success: boolean;
}

interface Session {
  id: string;
  ip_address: string;
  user_agent: string;
  last_active: string;
  is_current: boolean;
}

export default function SettingsPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'profile' | 'security' | 'storage' | 'activity' | 'backup'>('profile');
  
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

  // Audit logs
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

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

  useEffect(() => {
    if (activeTab === 'activity' && profile) {
      loadAuditLogs();
    }
  }, [activeTab, profile]);

  const loadProfile = async () => {
    try {
      console.log('Settings - Calling API with baseURL:', apiClient.defaults.baseURL);
      const response = await apiClient.get('/api/auth/me');
      console.log('Settings - Response data:', response.data);
      
      // Backend returns user object directly, not wrapped in {user: ...}
      const userData = response.data;
      console.log('Settings - User data:', userData);
      
      if (!userData || !userData.username) {
        console.error('Invalid user data:', userData);
        throw new Error('No valid user data received');
      }
      
      setProfile(userData);
      setEmail(userData.email || '');
      console.log('Settings - Profile set successfully');
    } catch (error) {
      console.error('Failed to load profile:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStorageQuota = async () => {
    try {
      const response = await apiClient.get('/api/system/quota');
      setStorageQuota(response.data);
    } catch (error) {
      console.error('Failed to load storage quota:', error);
    }
  };

  const loadAuditLogs = async () => {
    if (!profile) {
      console.log('Profile not loaded yet, skipping audit logs');
      return;
    }
    
    setLogsLoading(true);
    try {
      const response = await apiClient.get('/api/logging/audit', {
        params: {
          user_filter: profile.username,
          limit: 20,
          sort_order: 'desc'
        }
      });
      setAuditLogs(response.data.logs || []);
    } catch (error) {
      console.error('Failed to load audit logs:', error);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleUpdateEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    
    try {
      await apiClient.patch(`/api/users/${profile?.id}`, { email });
      alert('Email updated successfully');
      await loadProfile();
    } catch (error: any) {
      console.error('Failed to update email:', error);
      alert(error.response?.data?.detail || 'Failed to update email');
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
    } catch (error: any) {
      console.error('Failed to change password:', error);
      alert(error.response?.data?.detail || 'Failed to change password');
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
    } catch (error: any) {
      console.error('Failed to upload avatar:', error);
      alert(error.response?.data?.detail || 'Failed to upload avatar');
    } finally {
      setSaving(false);
    }
  };

  const handleExportData = async () => {
    try {
      alert('Data export feature coming soon!');
    } catch (error) {
      console.error('Failed to export data:', error);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };

  // Early returns for loading and error states
  if (loading || !profile) {
    return (
      <div className="text-center py-8 text-slate-400">
        {loading ? 'Loading...' : 'Failed to load profile'}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-white">Settings</h1>
        <p className="mt-1 text-sm text-slate-400">Manage your account settings and preferences</p>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-2 overflow-x-auto border-b border-slate-800">
        {[
          { id: 'profile', label: 'Profile', icon: User },
          { id: 'security', label: 'Security', icon: Lock },
          { id: 'storage', label: 'Storage', icon: HardDrive },
          { id: 'activity', label: 'Activity', icon: Activity },
          ...(profile?.role === 'admin' ? [{ id: 'backup', label: 'Backup', icon: Database }] : [])
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex items-center gap-2 px-4 py-3 font-medium transition-colors whitespace-nowrap border-b-2 ${
              activeTab === tab.id
                ? 'text-sky-400 border-sky-500'
                : 'text-slate-100-secondary border-transparent'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      <div className="w-full space-y-6">
        {/* Profile Tab */}
        {activeTab === 'profile' && (
          <>
            {/* Profile Card */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <div className="flex items-center space-x-4 mb-6">
                <div className="w-20 h-20 rounded-full flex items-center justify-center text-white text-2xl font-bold bg-gradient-to-br from-sky-500 to-violet-500">
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
                    Member since {new Date(profile.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
            </div>

            {/* Avatar Upload */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-lg font-semibold mb-4 flex items-center">
                <Image className="w-5 h-5 mr-2 text-sky-400" />
                Profile Picture
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Upload New Avatar</label>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleAvatarChange}
                    className="block w-full text-sm rounded-lg border border-slate-800 bg-slate-950-secondary text-slate-100-secondary px-3 py-2"
                  />
                </div>
                {avatarPreview && (
                  <div>
                    <p className="text-sm mb-2 text-slate-100-secondary">Preview:</p>
                    <img
                      src={avatarPreview}
                      alt="Avatar preview"
                      className="w-32 h-32 rounded-full object-cover"
                    />
                    <button
                      onClick={handleAvatarUpload}
                      disabled={saving}
                      className="mt-4 px-4 py-2 text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50"
                    >
                      {saving ? 'Uploading...' : 'Upload Avatar'}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Email Update */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-lg font-semibold mb-4 flex items-center">
                <Mail className="w-5 h-5 mr-2 text-sky-400" />
                Email Address
              </h3>
              <form onSubmit={handleUpdateEmail} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Email</label>
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
                  className="px-4 py-2 text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Update Email'}
                </button>
              </form>
            </div>

            {/* Account Info */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-lg font-semibold mb-4 flex items-center">
                <User className="w-5 h-5 mr-2 text-sky-400" />
                Account Information
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-slate-100-secondary">Username</label>
                  <p className="text-lg">{profile.username}</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-100-secondary">Role</label>
                  <p className="text-lg capitalize">{profile.role}</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-100-secondary">Account ID</label>
                  <p className="text-lg font-mono">{profile.id}</p>
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
              <h3 className="text-lg font-semibold mb-4 flex items-center">
                <Lock className="w-5 h-5 mr-2 text-sky-400" />
                Change Password
              </h3>
              <form onSubmit={handleChangePassword} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Current Password</label>
                  <input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="input"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">New Password</label>
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
                  <label className="block text-sm font-medium mb-1">Confirm New Password</label>
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
                  className="px-4 py-2 text-white rounded-lg transition-colors disabled:opacity-50 bg-sky-500 hover:bg-sky-500-secondary"
                >
                  {saving ? 'Changing...' : 'Change Password'}
                </button>
              </form>
            </div>

            {/* Active Sessions */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-lg font-semibold mb-4 flex items-center">
                <Clock className="w-5 h-5 mr-2 text-sky-400" />
                Active Sessions
              </h3>
              <div className="space-y-3">
                {sessions.map(session => (
                  <div
                    key={session.id}
                    className="p-4 rounded-lg border"
                    style={{
                      backgroundColor: 'var(--bg-secondary)',
                      borderColor: 'var(--border-primary)'
                    }}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="font-medium">{session.user_agent}</p>
                        <p className="text-sm text-slate-100-secondary">
                          IP: {session.ip_address}
                        </p>
                        <p className="text-sm text-slate-100-tertiary">
                          Last active: {formatDate(session.last_active)}
                        </p>
                      </div>
                      {session.is_current && (
                        <span className="px-2 py-1 text-xs rounded" style={{ backgroundColor: 'var(--success)', color: 'white' }}>
                          Current
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Data Export */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-lg font-semibold mb-4 flex items-center">
                <Download className="w-5 h-5 mr-2 text-sky-400" />
                Data Export
              </h3>
              <p className="mb-4 text-slate-100-secondary">
                Download all your personal data and files in a portable format.
              </p>
              <button
                onClick={handleExportData}
                className="px-4 py-2 text-white rounded-lg transition-colors bg-sky-500 hover:bg-sky-500-secondary"
              >
                Export My Data
              </button>
            </div>
          </>
        )}

        {/* Backup Tab (Admin only) */}
        {activeTab === 'backup' && profile?.role === 'admin' && (
          <BackupSettings />
        )}

        {/* Storage Tab */}
        {activeTab === 'storage' && (
          <>
            {/* Storage Quota */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-lg font-semibold mb-4 flex items-center">
                <HardDrive className="w-5 h-5 mr-2 text-sky-400" />
                Storage Usage
              </h3>
              {storageQuota ? (
                <>
                  <div className="mb-4">
                    <div className="flex justify-between mb-2">
                      <span className="text-slate-100-secondary">Used</span>
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
                      {formatBytes(storageQuota.quota_bytes - storageQuota.used_bytes)} remaining
                    </p>
                  )}
                  {!storageQuota.quota_bytes && (
                    <p className="text-sm text-slate-100-tertiary">
                      No storage limit set
                    </p>
                  )}
                </>
              ) : (
                <p className="text-slate-100-secondary">Loading storage information...</p>
              )}
            </div>

            {/* Storage Info */}
            <div className="card border-slate-800/60 bg-slate-900/55">
              <h3 className="text-lg font-semibold mb-4">Storage Tips</h3>
              <ul className="space-y-2 text-slate-100-secondary">
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Delete unnecessary files to free up space</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Use file compression for large archives</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Contact admin if you need more storage</span>
                </li>
              </ul>
            </div>
          </>
        )}

        {/* Activity Tab */}
        {activeTab === 'activity' && (
          <div className="card border-slate-800/60 bg-slate-900/55">
            <h3 className="text-lg font-semibold mb-4 flex items-center">
              <Activity className="w-5 h-5 mr-2 text-sky-400" />
              Recent Activity
            </h3>
            {logsLoading ? (
              <p className="text-slate-100-secondary">Loading activity...</p>
            ) : auditLogs.length > 0 ? (
              <div className="space-y-2">
                {auditLogs.map(log => (
                  <div
                    key={log.id}
                    className="p-3 rounded border bg-slate-950-secondary border-slate-800"
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="font-medium">{log.action.replace(/_/g, ' ')}</p>
                        {Object.keys(log.details).length > 0 && (
                          Array.isArray(log.details.disks) || typeof log.details.disks === 'object' ? (
                            <div className="mt-3">
                              <div className="overflow-x-auto rounded-xl border border-slate-800/60 bg-slate-950/40">
                                <table className="min-w-full text-xs">
                                  <thead>
                                    <tr className="border-b border-slate-800/60">
                                      <th className="px-4 py-3 text-left text-sky-400 font-semibold">Drive</th>
                                      <th className="px-4 py-3 text-left text-slate-400 font-medium">avg_read_mbps</th>
                                      <th className="px-4 py-3 text-left text-slate-400 font-medium">avg_write_mbps</th>
                                      <th className="px-4 py-3 text-left text-slate-400 font-medium">max_read_mbps</th>
                                      <th className="px-4 py-3 text-left text-slate-400 font-medium">max_write_mbps</th>
                                      <th className="px-4 py-3 text-left text-slate-400 font-medium">avg_read_iops</th>
                                      <th className="px-4 py-3 text-left text-slate-400 font-medium">avg_write_iops</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {Object.entries(log.details.disks).map(([drive, stats]: [string, any]) => (
                                      <tr
                                        key={drive}
                                        className="border-b border-slate-800/40 last:border-0 transition-colors hover:bg-slate-800/30"
                                      >
                                        <td className="px-4 py-3 font-mono text-emerald-400 font-semibold">{drive}</td>
                                        <td className="px-4 py-3 text-slate-300">{stats.avg_read_mbps}</td>
                                        <td className="px-4 py-3 text-slate-300">{stats.avg_write_mbps}</td>
                                        <td className="px-4 py-3 text-slate-300">{stats.max_read_mbps}</td>
                                        <td className="px-4 py-3 text-slate-300">{stats.max_write_mbps}</td>
                                        <td className="px-4 py-3 text-slate-300">{stats.avg_read_iops}</td>
                                        <td className="px-4 py-3 text-slate-300">{stats.avg_write_iops}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                              {log.details.interval_seconds && (
                                <div className="text-xs text-slate-500 mt-2">Interval: {log.details.interval_seconds}s</div>
                              )}
                            </div>
                          ) : (
                            <pre className="text-xs bg-slate-950/60 border border-slate-800/60 rounded-lg p-3 mt-2 overflow-x-auto text-emerald-400">
                              {JSON.stringify(log.details, null, 2)}
                            </pre>
                          )
                        )}
                      </div>
                      <span
                        className="text-xs px-2 py-1 rounded font-medium"
                        style={{
                          backgroundColor: log.success ? '#10b981' : '#ef4444',
                          color: '#ffffff'
                        }}
                      >
                        {log.success ? 'Success' : 'Failed'}
                      </span>
                    </div>
                    <p className="text-xs mt-1 text-slate-100-tertiary">
                      {formatDate(log.timestamp)}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-100-secondary">No activity logs found</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
