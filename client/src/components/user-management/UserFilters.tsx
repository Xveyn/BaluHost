import { useTranslation } from 'react-i18next';
import { Search, Trash2 } from 'lucide-react';

interface UserFiltersProps {
  searchTerm: string;
  onSearchChange: (s: string) => void;
  roleFilter: string;
  onRoleFilterChange: (r: string) => void;
  statusFilter: string;
  onStatusFilterChange: (s: string) => void;
  selectedCount: number;
  onBulkDelete: () => void;
}

export function UserFilters({
  searchTerm,
  onSearchChange,
  roleFilter,
  onRoleFilterChange,
  statusFilter,
  onStatusFilterChange,
  selectedCount,
  onBulkDelete,
}: UserFiltersProps) {
  const { t } = useTranslation('admin');

  return (
    <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
      <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
        <div className="flex-1 min-w-0">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder={t('users.placeholders.search')}
              value={searchTerm}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 py-2 pl-10 pr-4 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>
        </div>

        <div className="flex gap-2">
          <select
            value={roleFilter}
            onChange={(e) => onRoleFilterChange(e.target.value)}
            className="flex-1 sm:flex-initial rounded-lg border border-slate-700 bg-slate-900/70 px-3 sm:px-4 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            <option value="">{t('users.filters.allRoles')}</option>
            <option value="admin">{t('users.roles.admin')}</option>
            <option value="user">{t('users.roles.user')}</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => onStatusFilterChange(e.target.value)}
            className="flex-1 sm:flex-initial rounded-lg border border-slate-700 bg-slate-900/70 px-3 sm:px-4 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            <option value="">{t('users.filters.allStatus')}</option>
            <option value="true">{t('users.status.active')}</option>
            <option value="false">{t('users.status.inactive')}</option>
          </select>
        </div>
      </div>

      {selectedCount > 0 && (
        <div className="mt-4 flex items-center justify-between rounded-lg border border-rose-900/60 bg-rose-950/30 p-3">
          <span className="text-sm text-rose-200">
            {t('users.bulk.selected', { count: selectedCount })}
          </span>
          <button
            onClick={onBulkDelete}
            className="flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
          >
            <Trash2 className="h-4 w-4" />
            {t('users.buttons.deleteSelected')}
          </button>
        </div>
      )}
    </div>
  );
}
