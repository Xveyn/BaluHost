import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { KeyRound, Plus, Trash2, Copy, Check, AlertTriangle, Clock, User } from 'lucide-react';
import {
  listApiKeys,
  createApiKey,
  revokeApiKey,
  getEligibleUsers,
  getKeyStatus,
  type ApiKeyPublic,
  type ApiKeyCreated,
  type EligibleUser,
} from '../../api/api-keys';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';

const EXPIRY_OPTIONS = [
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
  { value: 365, label: '1 year' },
  { value: 0, label: 'No expiration' },
];

function StatusBadge({ apiKey }: { apiKey: ApiKeyPublic }) {
  const { t } = useTranslation('settings');
  const status = getKeyStatus(apiKey);

  const styles = {
    active: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    revoked: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
    expired: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${styles[status]}`}>
      {t(`apiKeys.status.${status}`)}
    </span>
  );
}

export default function ApiKeysTab() {
  const { t } = useTranslation('settings');
  const { confirm, dialog } = useConfirmDialog();

  const [keys, setKeys] = useState<ApiKeyPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Create dialog state
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createTargetUserId, setCreateTargetUserId] = useState<number | ''>('');
  const [createExpiry, setCreateExpiry] = useState<number>(90);
  const [eligibleUsers, setEligibleUsers] = useState<EligibleUser[]>([]);
  const [creating, setCreating] = useState(false);

  // Key reveal state
  const [revealedKey, setRevealedKey] = useState<ApiKeyCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const loadKeys = useCallback(async () => {
    try {
      const data = await listApiKeys();
      setKeys(data.keys);
      setError('');
    } catch {
      setError(t('apiKeys.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const loadEligibleUsers = useCallback(async () => {
    try {
      const users = await getEligibleUsers();
      setEligibleUsers(users);
      if (users.length > 0 && createTargetUserId === '') {
        setCreateTargetUserId(users[0].id);
      }
    } catch {
      // Silently fail - users can still enter an ID
    }
  }, [createTargetUserId]);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  const handleOpenCreate = () => {
    setShowCreate(true);
    setCreateName('');
    setCreateExpiry(90);
    loadEligibleUsers();
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createName.trim() || createTargetUserId === '') return;

    setCreating(true);
    setError('');
    try {
      const result = await createApiKey({
        name: createName.trim(),
        target_user_id: Number(createTargetUserId),
        expires_in_days: createExpiry === 0 ? null : createExpiry,
      });
      setRevealedKey(result);
      setShowCreate(false);
      loadKeys();
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || t('apiKeys.createFailed'));
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (key: ApiKeyPublic) => {
    const confirmed = await confirm(
      `${t('apiKeys.revokeConfirm')} "${key.name}" (${key.key_prefix}...)?`,
      { title: t('apiKeys.revoke'), variant: 'danger', confirmLabel: t('apiKeys.revoke') },
    );
    if (!confirmed) return;

    try {
      await revokeApiKey(key.id);
      loadKeys();
    } catch {
      setError(t('apiKeys.revokeFailed'));
    }
  };

  const handleCopyKey = async () => {
    if (!revealedKey) return;
    try {
      await navigator.clipboard.writeText(revealedKey.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select the text
    }
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return '-';
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55 p-6">
        <p className="text-slate-400 text-sm">{t('apiKeys.loading')}</p>
      </div>
    );
  }

  // Key reveal modal
  if (revealedKey) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
          <KeyRound className="w-5 h-5 mr-2 text-amber-400" />
          {t('apiKeys.keyCreated')}
        </h3>

        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 mb-4 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>{t('apiKeys.keyRevealWarning')}</span>
        </div>

        <div className="mb-2 text-sm text-slate-400">{t('apiKeys.keyLabel')}</div>
        <div className="flex items-center gap-2 mb-4">
          <code className="flex-1 px-3 py-2.5 rounded-lg bg-slate-800/80 border border-slate-700/50 font-mono text-sm text-emerald-300 break-all select-all">
            {revealedKey.key}
          </code>
          <button
            onClick={handleCopyKey}
            className="flex-shrink-0 p-2.5 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors touch-manipulation active:scale-95"
            title={t('apiKeys.copy')}
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4 text-slate-300" />}
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm mb-4">
          <div>
            <span className="text-slate-400">{t('apiKeys.nameLabel')}</span>
            <p className="font-medium">{revealedKey.name}</p>
          </div>
          <div>
            <span className="text-slate-400">{t('apiKeys.targetUser')}</span>
            <p className="font-medium">{revealedKey.target_username}</p>
          </div>
        </div>

        <button
          onClick={() => { setRevealedKey(null); setCopied(false); }}
          className="w-full px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-600 transition-colors touch-manipulation active:scale-95"
        >
          {t('apiKeys.done')}
        </button>
      </div>
    );
  }

  return (
    <>
      {dialog}

      {/* Header */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div>
            <h3 className="text-base sm:text-lg font-semibold flex items-center">
              <KeyRound className="w-5 h-5 mr-2 text-sky-400" />
              {t('apiKeys.title')}
            </h3>
            <p className="text-sm text-slate-400 mt-1">{t('apiKeys.description')}</p>
          </div>
          <button
            onClick={handleOpenCreate}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium text-white rounded-lg bg-sky-500 hover:bg-sky-600 transition-colors touch-manipulation active:scale-95"
          >
            <Plus className="w-4 h-4" />
            {t('apiKeys.create')}
          </button>
        </div>

        {error && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
            {error}
          </div>
        )}

        {/* Create form */}
        {showCreate && (
          <form onSubmit={handleCreate} className="mb-4 p-4 rounded-xl border border-slate-700/50 bg-slate-800/40 space-y-3">
            <div>
              <label className="block text-sm font-medium mb-1">{t('apiKeys.nameLabel')}</label>
              <input
                type="text"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                className="input"
                placeholder={t('apiKeys.namePlaceholder')}
                maxLength={100}
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">{t('apiKeys.targetUser')}</label>
              <select
                value={createTargetUserId}
                onChange={(e) => setCreateTargetUserId(Number(e.target.value))}
                className="input"
                required
              >
                {eligibleUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.username} ({u.role})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">{t('apiKeys.expiration')}</label>
              <select
                value={createExpiry}
                onChange={(e) => setCreateExpiry(Number(e.target.value))}
                className="input"
              >
                {EXPIRY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="flex-1 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors touch-manipulation active:scale-95"
              >
                {t('apiKeys.cancel')}
              </button>
              <button
                type="submit"
                disabled={creating || !createName.trim() || createTargetUserId === ''}
                className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-600 transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
              >
                {creating ? t('apiKeys.creating') : t('apiKeys.create')}
              </button>
            </div>
          </form>
        )}

        {/* Key list */}
        {keys.length === 0 ? (
          <div className="text-center py-8 text-slate-400">
            <KeyRound className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p className="text-sm">{t('apiKeys.noKeys')}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {keys.map((key) => (
              <div
                key={key.id}
                className="p-3 sm:p-4 rounded-lg border border-slate-700/40 bg-slate-800/40"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm truncate">{key.name}</span>
                      <StatusBadge apiKey={key} />
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
                      <span className="font-mono">{key.key_prefix}...</span>
                      <span className="flex items-center gap-1">
                        <User className="w-3 h-3" />
                        {key.target_username}
                      </span>
                      {key.last_used_at && (
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatDate(key.last_used_at)}
                        </span>
                      )}
                      <span>{key.use_count} {t('apiKeys.uses')}</span>
                    </div>
                    {key.expires_at && (
                      <p className="mt-1 text-xs text-slate-500">
                        {t('apiKeys.expiresAt')}: {formatDate(key.expires_at)}
                      </p>
                    )}
                  </div>

                  {key.is_active && (
                    <button
                      onClick={() => handleRevoke(key)}
                      className="flex-shrink-0 p-2 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors touch-manipulation active:scale-95"
                      title={t('apiKeys.revoke')}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
