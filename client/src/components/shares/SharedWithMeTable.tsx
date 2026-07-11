import { useTranslation } from 'react-i18next';
import { Share2, Users, Calendar } from 'lucide-react';
import { SortableHeader } from '../ui/SortableHeader';
import { EmptyState } from '../ui/EmptyState';
import { PermissionBadges } from './PermissionBadges';
import { FileNameCell } from './FileNameCell';
import { formatDate } from './sharesFormat';
import type { SharedWithMe } from '../../api/shares';
import type { SortProps } from './types';

interface SharedWithMeTableProps extends SortProps {
  items: SharedWithMe[];
  allCount: number;
}

const th = 'px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider';

export function SharedWithMeTable({ items, allCount, sortKey, sortDirection, onSort }: SharedWithMeTableProps) {
  const { t } = useTranslation(['shares', 'common']);
  const never = t('common:time.never');
  const folderLabel = t('form.folder');

  if (items.length === 0) {
    return (
      <EmptyState
        icon={Share2}
        title={allCount === 0 ? t('empty.noFilesShared') : t('empty.noMatchingFilesShared')}
        description={allCount === 0 ? t('empty.noFilesSharedDesc') : t('empty.tryAdjusting')}
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
              <th className={th}>{t('table.permissions')}</th>
              <SortableHeader label={t('table.shared')} sortKey="shared_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
              <SortableHeader label={t('table.expires')} sortKey="expires_at" activeSortKey={sortKey} sortDirection={sortDirection} onSort={onSort} className={th} />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {items.map((item) => (
              <tr key={item.share_id} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <FileNameCell isDirectory={item.is_directory} name={item.file_name} size={item.file_size} folderLabel={folderLabel} />
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{item.owner_username}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4">
                  <div className="flex space-x-1">
                    <PermissionBadges canRead={item.can_read} canWrite={item.can_write} canDelete={item.can_delete} />
                  </div>
                </td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(item.shared_at, never)}</td>
                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">{formatDate(item.expires_at, never)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="lg:hidden space-y-3">
        {items.map((item) => (
          <div key={item.share_id} className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4">
            <FileNameCell variant="card" className="mb-2" isDirectory={item.is_directory} name={item.file_name} size={item.file_size} folderLabel={folderLabel} />
            <div className="flex items-center gap-2 mb-2">
              <Users className="h-3 w-3 text-slate-400" />
              <span className="text-sm text-slate-300">{t('table.from')}: {item.owner_username}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <PermissionBadges size="sm" canRead={item.can_read} canWrite={item.can_write} canDelete={item.can_delete} />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {t('table.shared')}: {formatDate(item.shared_at, never)}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {t('table.expires')}: {formatDate(item.expires_at, never)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
