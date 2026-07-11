import { useTranslation } from 'react-i18next';
import { Search, Filter, Users } from 'lucide-react';

type StatusFilter = 'all' | 'active' | 'expired';

interface SharesToolbarProps {
  searchQuery: string;
  onSearch: (v: string) => void;
  statusFilter: StatusFilter;
  onStatusFilter: (v: StatusFilter) => void;
  showFilters: boolean;
  onToggleFilters: () => void;
  showCreateButton: boolean;
  onCreate: () => void;
}

export function SharesToolbar({
  searchQuery, onSearch, statusFilter, onStatusFilter,
  showFilters, onToggleFilters, showCreateButton, onCreate,
}: SharesToolbarProps) {
  const { t } = useTranslation(['shares', 'common']);

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 sm:w-5 sm:h-5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearch(e.target.value)}
            placeholder={t('search.placeholder')}
            className="w-full pl-10 sm:pl-11 pr-4 py-2.5 sm:py-3 border border-slate-700 bg-slate-900/70 rounded-xl focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all text-slate-200 placeholder-slate-500 text-sm sm:text-base"
          />
        </div>

        <button
          onClick={onToggleFilters}
          className={`px-4 sm:px-5 py-2.5 sm:py-3 border rounded-xl flex items-center justify-center gap-2 font-medium transition-all touch-manipulation active:scale-95 text-sm sm:text-base ${
            showFilters ? 'bg-blue-500/20 border-blue-500/40 text-blue-400' : 'border-slate-700 text-slate-300 hover:bg-slate-800/50'
          }`}
        >
          <Filter className="w-4 h-4 sm:w-5 sm:h-5" />
          <span>{t('search.filters')}</span>
        </button>

        {showCreateButton && (
          <button
            onClick={onCreate}
            className="btn btn-primary flex items-center justify-center gap-2 touch-manipulation active:scale-95"
          >
            <Users className="w-4 h-4 sm:w-5 sm:h-5" />
            <span className="hidden sm:inline">{t('buttons.shareWithUser')}</span>
            <span className="sm:hidden">{t('buttons.share')}</span>
          </button>
        )}
      </div>

      {showFilters && (
        <div className="flex flex-wrap gap-2 sm:gap-3 p-3 sm:p-4 bg-slate-800/30 rounded-xl border border-slate-700/50">
          <span className="text-xs sm:text-sm font-semibold text-slate-300 flex items-center mr-2">
            {t('search.status')}:
          </span>
          {(['all', 'active', 'expired'] as const).map((status) => (
            <label key={status} className="flex items-center cursor-pointer">
              <input
                type="radio"
                value={status}
                checked={statusFilter === status}
                onChange={(e) => onStatusFilter(e.target.value as StatusFilter)}
                className="mr-1.5 sm:mr-2 w-4 h-4 text-sky-500"
              />
              <span className="text-xs sm:text-sm font-medium text-slate-300 capitalize">{t(`search.${status}`)}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
