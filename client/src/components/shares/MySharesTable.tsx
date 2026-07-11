// client/src/components/shares/MySharesTable.tsx
import { useTranslation } from 'react-i18next';
import { Users, Edit, Trash2, Calendar } from 'lucide-react';
import { SortableHeader } from '../ui/SortableHeader';
import { EmptyState } from '../ui/EmptyState';
import { PermissionBadges } from './PermissionBadges';
import { FileNameCell } from './FileNameCell';
import { formatDate } from './sharesFormat';
import type { FileShare } from '../../api/shares';
import type { SortProps } from './types';

interface MySharesTableProps extends SortProps {
  shares: FileShare[];
  allCount: number;
  onEdit: (share: FileShare) => void;
  onDelete: (shareId: number) => void;
}

const th = 'px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider';

export function MySharesTable({ shares, allCount, sortKey, sortDirection, onSort, onEdit, onDelete }: MySharesTableProps) {
  const { t } = useTranslation(['shares', 'common']);
  const never = t('common:time.never');
  const folderLabel = t('form.folder');

  if (shares.length === 0) {
    return (
      <EmptyState
        icon={Users}
        title={allCount === 0 ? t('empty.noShares') : t('empty.noMatchingShares')}
        description={allCount === 0 ? t('empty.noSharesDesc') : t('empty.tryAdjusting')}
      />
    );
  }

  return (
    <>
      {/* Desktop Table */}
      <div className="hidden lg:block overflow-x-auto">
        <table className="min-w-full">
          <thead className="bg-slate-800/30 border-b border-slate-700/50">
            <tr>
              <SortableHeader label={t('table.file')} sortKey="file_name" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.owner')} sortKey="owner_username" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.sharedWith')} sortKey="shared_with_username" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <th className={th}>{t('table.permissions')}</th>
              <SortableHeader label={t('table.expires')} sortKey="expires_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <th className={th}>{t('table.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {shares.map((share) => (
              <tr key={share.id} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <FileNameCell isDirectory={share.is_directory} name={share.file_name} size={share.file_size} folderLabel={folderLabel} />
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{share.owner_username}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{share.shared_with_username}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <div className="flex space-x-1">
                    <PermissionBadges canRead={share.can_read} canWrite={share.can_write} canDelete={share.can_delete} />
                  </div>
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(share.expires_at, never)}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <div className="flex space-x-1">
                    <button onClick={() => onEdit(share)} className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition hover:border-green-500/50 hover:bg-green-500/20" title={t('buttons.edit')}>
                      <Edit className="w-4 h-4 sm:w-5 sm:h-5" />
                    </button>
                    <button onClick={() => onDelete(share.id)} className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20" title={t('buttons.revoke')}>
                      <Trash2 className="w-4 h-4 sm:w-5 sm:h-5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="lg:hidden space-y-3">
        {shares.map((share) => (
          <div key={share.id} className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4">
            <div className="flex items-start justify-between gap-2 mb-3">
              <FileNameCell variant="card" className="min-w-0 flex-1" isDirectory={share.is_directory} name={share.file_name} size={share.file_size} folderLabel={folderLabel} />
              <div className="flex gap-1 flex-shrink-0">
                <button onClick={() => onEdit(share)} className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition touch-manipulation active:scale-95" title={t('buttons.edit')}>
                  <Edit className="w-4 h-4" />
                </button>
                <button onClick={() => onDelete(share.id)} className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition touch-manipulation active:scale-95" title={t('buttons.revoke')}>
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Users className="h-3 w-3 text-slate-400" />
              <span className="text-sm text-slate-300">{t('table.owner')}: {share.owner_username}</span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Users className="h-3 w-3 text-slate-400" />
              <span className="text-sm text-slate-300">{share.shared_with_username}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <PermissionBadges size="sm" canRead={share.can_read} canWrite={share.can_write} canDelete={share.can_delete} />
            </div>
            <div className="text-xs text-slate-400 flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {t('table.expires')}: {formatDate(share.expires_at, never)}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
