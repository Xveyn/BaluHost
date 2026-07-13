import { useTranslation } from 'react-i18next'
import { Table, BarChart3, Database, History, Wrench, Timer } from 'lucide-react'
import type { AnalyticsTabType } from './AnalyticsContent'

export type CategoryType = 'browse' | 'analytics'

interface DatabaseCategoryNavProps {
  activeCategory: CategoryType
  onCategoryChange: (category: CategoryType) => void
  analyticsTab: AnalyticsTabType
  onAnalyticsTabChange: (tab: AnalyticsTabType) => void
}

/**
 * Two-level navigation: Browse/Analytics category pills plus (when Analytics is
 * active) the analytics sub-tab bar. Extracted verbatim from AdminDatabase.
 */
export default function DatabaseCategoryNav({
  activeCategory,
  onCategoryChange,
  analyticsTab,
  onAnalyticsTabChange,
}: DatabaseCategoryNavProps) {
  const { t } = useTranslation('admin')

  const analyticsTabs = [
    { id: 'stats' as AnalyticsTabType, label: t('database.tabs.stats'), icon: BarChart3 },
    { id: 'storage' as AnalyticsTabType, label: t('database.tabs.storage'), icon: Database },
    { id: 'history' as AnalyticsTabType, label: t('database.tabs.history'), icon: History },
    { id: 'maintenance' as AnalyticsTabType, label: t('database.tabs.maintenance'), icon: Wrench },
    { id: 'retention' as AnalyticsTabType, label: t('database.tabs.retention'), icon: Timer },
  ]

  return (
    <div className="space-y-3">
      {/* Category Pills */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
        <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
          <button
            onClick={() => onCategoryChange('browse')}
            className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
              activeCategory === 'browse'
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
            }`}
          >
            <Table className="h-4 w-4 sm:h-5 sm:w-5" />
            <span>Browse</span>
          </button>
          <button
            onClick={() => onCategoryChange('analytics')}
            className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
              activeCategory === 'analytics'
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
            }`}
          >
            <BarChart3 className="h-4 w-4 sm:h-5 sm:w-5" />
            <span>Analytics</span>
          </button>
        </div>
      </div>

      {/* Sub-Tabs (only for Analytics) */}
      {activeCategory === 'analytics' && (
        <div className="relative">
          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
            <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0 sm:flex-wrap">
              {analyticsTabs.map((tab) => {
                const Icon = tab.icon
                return (
                  <button
                    key={tab.id}
                    onClick={() => onAnalyticsTabChange(tab.id)}
                    className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                      analyticsTab === tab.id
                        ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                        : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
                    }`}
                  >
                    <Icon className="w-4 h-4 sm:w-5 sm:h-5" />
                    <span>{tab.label}</span>
                  </button>
                )
              })}
            </div>
          </div>
          {/* Fade-Gradient rechts — nur mobile */}
          <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-950 to-transparent sm:hidden" />
        </div>
      )}
    </div>
  )
}
