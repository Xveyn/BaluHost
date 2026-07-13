import type { ApiCategory } from '../../../lib/openapi-transform';
import type { ApiSection } from '../../../data/api-endpoints/types';

export interface ApiCategoryTabsProps {
  apiSections: ApiSection[];
  apiCategories: ApiCategory[];
  selectedCategory: string | null;
  selectedSection: string | null;
  currentCategorySections: ApiSection[];
  onSelectCategory: (id: string | null) => void;
  onSelectSection: (title: string | null) => void;
  t: (key: string) => string;
}

export function ApiCategoryTabs({
  apiSections,
  apiCategories,
  selectedCategory,
  selectedSection,
  currentCategorySections,
  onSelectCategory,
  onSelectSection,
  t,
}: ApiCategoryTabsProps) {
  return (
    <div className="space-y-3">
      {/* Category Pills */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
        <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
          <button
            onClick={() => onSelectCategory(null)}
            className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
              !selectedCategory
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
            }`}
          >
            <span>{t('system:apiCenter.all')}</span>
            <span className="text-[10px] opacity-70">({apiSections.reduce((sum, s) => sum + s.endpoints.length, 0)})</span>
          </button>
          {apiCategories.map((cat) => {
            const endpointCount = cat.sections.reduce((sum, s) => sum + s.endpoints.length, 0);
            return (
              <button
                key={cat.id}
                onClick={() => onSelectCategory(cat.id)}
                className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                  selectedCategory === cat.id
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                    : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
                }`}
              >
                <span>{cat.label}</span>
                <span className="text-[10px] opacity-70">({endpointCount})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Sub-Tabs (only for active category) */}
      {selectedCategory && currentCategorySections.length > 0 && (
        <div className="relative">
          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
            <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0 sm:flex-wrap">
              <button
                onClick={() => onSelectSection(null)}
                className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                  !selectedSection
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                    : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
                }`}
              >
                <span>{t('system:apiCenter.all')}</span>
              </button>
              {currentCategorySections.map((section) => (
                <button
                  key={section.title}
                  onClick={() => onSelectSection(section.title)}
                  className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                    selectedSection === section.title
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
                  }`}
                >
                  {section.icon}
                  <span>{section.title}</span>
                  <span className="text-[10px] opacity-70">({section.endpoints.length})</span>
                </button>
              ))}
            </div>
          </div>
          {/* Fade gradient right - mobile only */}
          <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-950 to-transparent sm:hidden" />
        </div>
      )}
    </div>
  );
}
