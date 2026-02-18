/**
 * OwnershipTransferModal component -- modal for transferring file/folder ownership.
 */

import { useState } from 'react';
import { X, UserCheck, AlertTriangle, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { transferOwnership, type OwnershipTransferResponse } from '../../lib/api';
import type { FileItem } from './types';

interface OwnershipTransferModalProps {
  file: FileItem;
  allUsers: Array<{ id: string; username: string }>;
  currentUserId: number;
  onClose: () => void;
  onSuccess: (response: OwnershipTransferResponse) => void;
}

type ConflictStrategy = 'rename' | 'skip' | 'overwrite';

export function OwnershipTransferModal({
  file,
  allUsers,
  currentUserId,
  onClose,
  onSuccess,
}: OwnershipTransferModalProps) {
  const { t } = useTranslation(['fileManager', 'common']);
  const [selectedUserId, setSelectedUserId] = useState<string>('');
  const [recursive, setRecursive] = useState(true);
  const [conflictStrategy, setConflictStrategy] = useState<ConflictStrategy>('rename');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter out current owner from user list
  const availableUsers = allUsers.filter(
    u => Number(u.id) !== (file.ownerId ?? currentUserId)
  );

  const handleTransfer = async () => {
    if (!selectedUserId) {
      setError(t('fileManager:ownership.selectUser'));
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await transferOwnership({
        path: file.path,
        new_owner_id: Number(selectedUserId),
        recursive,
        conflict_strategy: conflictStrategy,
      });

      if (response.success) {
        onSuccess(response);
      } else {
        setError(response.message || t('fileManager:ownership.transferError'));
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      let message: string;
      if (typeof detail === 'string') {
        message = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        message = detail.map((e: any) => e.msg ?? String(e)).join('; ');
      } else {
        message = err?.message || t('fileManager:ownership.transferError');
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const selectedUser = availableUsers.find(u => u.id === selectedUserId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl p-4">
      <div className="card w-full max-w-lg flex flex-col border-indigo-500/30 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(0,0,0,0.5)]">
        {/* Header */}
        <div className="flex-shrink-0 flex items-center justify-between pb-4 border-b border-slate-800/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/20 text-indigo-400">
              <UserCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">
                {t('fileManager:ownership.title')}
              </h3>
              <p className="mt-0.5 text-xs text-slate-400 truncate max-w-[300px]">
                {file.name}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={loading}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="mt-5 space-y-5">
          {/* User Selection */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              {t('fileManager:ownership.newOwner')}
            </label>
            <select
              value={selectedUserId}
              onChange={e => setSelectedUserId(e.target.value)}
              disabled={loading}
              className="input w-full"
            >
              <option value="">{t('fileManager:ownership.selectUser')}</option>
              {availableUsers.map(u => (
                <option key={u.id} value={u.id}>
                  {u.username}
                </option>
              ))}
            </select>
          </div>

          {/* Recursive Option (only for directories) */}
          {file.type === 'directory' && (
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={recursive}
                onChange={e => setRecursive(e.target.checked)}
                disabled={loading}
                className="h-4 w-4 rounded border-slate-600 bg-slate-800/50 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0 cursor-pointer"
              />
              <span className="text-sm text-slate-300">
                {t('fileManager:ownership.recursive')}
              </span>
            </label>
          )}

          {/* Conflict Strategy */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              {t('fileManager:ownership.conflictStrategy')}
            </label>
            <div className="flex flex-wrap gap-3">
              {(['rename', 'skip', 'overwrite'] as ConflictStrategy[]).map(strategy => (
                <label key={strategy} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="conflictStrategy"
                    value={strategy}
                    checked={conflictStrategy === strategy}
                    onChange={() => setConflictStrategy(strategy)}
                    disabled={loading}
                    className="h-4 w-4 border-slate-600 bg-slate-800/50 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0 cursor-pointer"
                  />
                  <span className="text-sm text-slate-300">
                    {t(`fileManager:ownership.strategy.${strategy}`)}
                  </span>
                </label>
              ))}
            </div>
            {conflictStrategy === 'overwrite' && (
              <div className="mt-2 flex items-center gap-2 text-amber-400 text-xs">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>{t('fileManager:ownership.overwriteWarning')}</span>
              </div>
            )}
          </div>

          {/* Info Box */}
          {selectedUser && (
            <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
              <p className="text-sm text-slate-300">
                {t('fileManager:ownership.transferInfo', {
                  name: file.name,
                  user: selectedUser.username,
                })}
              </p>
              {file.type === 'directory' && recursive && (
                <p className="mt-1 text-xs text-slate-400">
                  {t('fileManager:ownership.recursiveInfo')}
                </p>
              )}
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex-shrink-0 flex items-center justify-end gap-3 pt-5 mt-5 border-t border-slate-800/60">
          <button
            onClick={onClose}
            disabled={loading}
            className="btn-ghost"
          >
            {t('common:cancel')}
          </button>
          <button
            onClick={handleTransfer}
            disabled={loading || !selectedUserId}
            className="btn-primary"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{t('common:loading')}</span>
              </>
            ) : (
              <>
                <UserCheck className="w-4 h-4" />
                <span>{t('fileManager:ownership.transfer')}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
