import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  HardDrive, Copy, Check, Monitor, Apple, Terminal,
  Loader2, AlertCircle, Users, ToggleLeft, ToggleRight,
  RefreshCw, Lock,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getSambaStatus,
  getSambaUsers,
  toggleSmbUser,
  getSambaConnectionInfo,
  type SambaStatus,
  type SambaUserStatus,
  type SambaConnectionInfo,
} from '../../api/samba';

const OS_ICONS: Record<string, React.ReactNode> = {
  windows: <Monitor className="h-5 w-5" />,
  macos: <Apple className="h-5 w-5" />,
  linux: <Terminal className="h-5 w-5" />,
};

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation('system');
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Failed to copy');
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 rounded-md bg-slate-700/50 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? t('samba.copied') : t('samba.copy')}
    </button>
  );
}

export default function SambaManagementCard() {
  const { t } = useTranslation('system');
  const [status, setStatus] = useState<SambaStatus | null>(null);
  const [users, setUsers] = useState<SambaUserStatus[]>([]);
  const [connectionInfo, setConnectionInfo] = useState<SambaConnectionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [togglingUser, setTogglingUser] = useState<number | null>(null);

  // Password modal state
  const [passwordModal, setPasswordModal] = useState<{ userId: number; username: string } | null>(null);
  const [passwordInput, setPasswordInput] = useState('');

  const loadData = useCallback(async () => {
    try {
      const [statusData, usersData, connInfo] = await Promise.all([
        getSambaStatus(),
        getSambaUsers(),
        getSambaConnectionInfo(),
      ]);
      setStatus(statusData);
      setUsers(usersData.users);
      setConnectionInfo(connInfo);
      setError(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleToggle = async (user: SambaUserStatus) => {
    const newEnabled = !user.smb_enabled;

    // When enabling, show password modal for optional sync
    if (newEnabled) {
      setPasswordModal({ userId: user.user_id, username: user.username });
      setPasswordInput('');
      return;
    }

    // Disabling — no password needed
    setTogglingUser(user.user_id);
    try {
      await toggleSmbUser(user.user_id, false);
      toast.success(t('samba.userDisabled', { username: user.username }));
      await loadData();
    } catch {
      toast.error(t('samba.toggleFailed'));
    } finally {
      setTogglingUser(null);
    }
  };

  const handleEnableConfirm = async () => {
    if (!passwordModal) return;

    setTogglingUser(passwordModal.userId);
    setPasswordModal(null);
    try {
      await toggleSmbUser(
        passwordModal.userId,
        true,
        passwordInput || undefined,
      );
      toast.success(t('samba.userEnabled', { username: passwordModal.username }));
      await loadData();
    } catch {
      toast.error(t('samba.toggleFailed'));
    } finally {
      setTogglingUser(null);
      setPasswordInput('');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        {t('samba.loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-red-400">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <HardDrive className="h-6 w-6 text-blue-400" />
            {t('samba.title')}
          </h2>
          <p className="mt-1 text-sm text-slate-400">{t('samba.subtitle')}</p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-1.5 rounded-lg bg-slate-800/50 px-3 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-700/50 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          {t('samba.refresh')}
        </button>
      </div>

      {/* Status Card */}
      {status && (
        <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
          <div className="flex flex-wrap items-center gap-4">
            {/* Running Status */}
            <div className="flex items-center gap-2">
              <div className={`h-2.5 w-2.5 rounded-full ${status.is_running ? 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.4)]' : 'bg-red-400'}`} />
              <span className={`text-sm font-medium ${status.is_running ? 'text-green-400' : 'text-red-400'}`}>
                {status.is_running ? t('samba.running') : t('samba.notRunning')}
              </span>
            </div>

            {/* Version */}
            {status.version && (
              <div className="flex items-center gap-1.5 text-sm text-slate-400">
                <span className="text-slate-500">{t('samba.version')}:</span>
                <span className="font-mono text-slate-300">{status.version}</span>
              </div>
            )}

            {/* Connections count */}
            <div className="flex items-center gap-1.5 text-sm text-slate-400">
              <Users className="h-3.5 w-3.5" />
              <span>{t('samba.connections')}: {status.active_connections.length}</span>
            </div>

            {/* SMB Users count */}
            <div className="flex items-center gap-1.5 text-sm text-slate-400">
              <span>{t('samba.enabledUsers')}: {status.smb_users_count}</span>
            </div>
          </div>

          {/* Active connections table */}
          {status.active_connections.length > 0 && (
            <div className="mt-4 border-t border-slate-700/50 pt-4">
              <h4 className="text-sm font-medium text-slate-300 mb-2">{t('samba.activeConnections')}</h4>
              <div className="space-y-1.5">
                {status.active_connections.map((conn, i) => (
                  <div key={i} className="flex items-center gap-4 text-xs text-slate-400 bg-slate-900/30 rounded-lg px-3 py-2">
                    <span className="font-mono">{conn.username}</span>
                    <span className="text-slate-600">from</span>
                    <span className="font-mono">{conn.machine}</span>
                    <span className="text-slate-600 ml-auto">PID {conn.pid}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Not running hint */}
      {status && !status.is_running && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 text-amber-300 text-sm">
          <AlertCircle className="h-4 w-4 inline mr-2" />
          {t('samba.notRunningHint')}
        </div>
      )}

      {/* User Management */}
      <div>
        <h3 className="text-base font-medium text-white mb-3 flex items-center gap-2">
          <Users className="h-5 w-5 text-slate-400" />
          {t('samba.userManagement')}
        </h3>
        <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700/50">
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">{t('samba.username')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">{t('samba.role')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">{t('samba.status')}</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-slate-400 uppercase tracking-wider">{t('samba.smbAccess')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/30">
              {users.map((user) => (
                <tr key={user.user_id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-3 text-sm text-white font-medium">{user.username}</td>
                  <td className="px-4 py-3 text-sm">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      user.role === 'admin'
                        ? 'bg-purple-500/20 text-purple-300'
                        : 'bg-blue-500/20 text-blue-300'
                    }`}>
                      {user.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <span className={`inline-flex items-center gap-1 text-xs ${user.is_active ? 'text-green-400' : 'text-slate-500'}`}>
                      <div className={`h-1.5 w-1.5 rounded-full ${user.is_active ? 'bg-green-400' : 'bg-slate-500'}`} />
                      {user.is_active ? t('samba.active') : t('samba.inactive')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => handleToggle(user)}
                      disabled={togglingUser === user.user_id || !user.is_active}
                      className="inline-flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      title={!user.is_active ? t('samba.inactiveUserHint') : undefined}
                    >
                      {togglingUser === user.user_id ? (
                        <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
                      ) : user.smb_enabled ? (
                        <ToggleRight className="h-6 w-6 text-green-400 hover:text-green-300" />
                      ) : (
                        <ToggleLeft className="h-6 w-6 text-slate-500 hover:text-slate-400" />
                      )}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mount Instructions */}
      {connectionInfo && (
        <div>
          <h3 className="text-base font-medium text-white mb-3">{t('samba.mountInstructions')}</h3>
          <p className="text-sm text-slate-400 mb-1">
            {t('samba.shareName')}: <code className="rounded bg-slate-900/50 px-1.5 py-0.5 text-xs font-mono text-blue-300">{connectionInfo.share_name}</code>
          </p>
          <p className="text-sm text-slate-400 mb-4">
            {t('samba.authenticateAs', { username: connectionInfo.username })}
          </p>

          {/* Capacity hint */}
          <div className="rounded-lg bg-green-500/10 border border-green-500/20 p-3 text-green-300 text-sm mb-4">
            <Check className="h-4 w-4 inline mr-2" />
            {t('samba.capacityHint')}
          </div>

          <div className="space-y-3">
            {connectionInfo.instructions.map((instr) => (
              <div key={instr.os} className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400">
                      {OS_ICONS[instr.os] || <Monitor className="h-5 w-5" />}
                    </span>
                    <span className="font-medium text-white">{instr.label}</span>
                  </div>
                  <CopyButton text={instr.command} />
                </div>

                <code className="block rounded-lg bg-slate-900/70 px-3 py-2.5 text-sm font-mono text-slate-300 border border-slate-700/30 break-all">
                  {instr.command}
                </code>

                {instr.notes && (
                  <p className="mt-2 text-xs text-slate-500">{instr.notes}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Password Modal */}
      {passwordModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 border border-slate-700/50 p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-1">
              <Lock className="h-5 w-5 text-blue-400" />
              {t('samba.enableSmbTitle', { username: passwordModal.username })}
            </h3>
            <p className="text-sm text-slate-400 mb-4">
              {t('samba.enableSmbDescription')}
            </p>

            <div className="mb-4">
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                {t('samba.passwordLabel')}
              </label>
              <input
                type="password"
                value={passwordInput}
                onChange={(e) => setPasswordInput(e.target.value)}
                placeholder={t('samba.passwordPlaceholder')}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleEnableConfirm();
                  if (e.key === 'Escape') setPasswordModal(null);
                }}
              />
              <p className="mt-1.5 text-xs text-slate-500">
                {t('samba.passwordHint')}
              </p>
            </div>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setPasswordModal(null)}
                className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                {t('samba.cancel')}
              </button>
              <button
                onClick={handleEnableConfirm}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
              >
                {t('samba.enable')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
