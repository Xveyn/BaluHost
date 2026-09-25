// client/src/components/dashboard/panels/PanelEmpty.tsx
import { useTranslation } from 'react-i18next';

interface PanelEmptyProps {
  title: string;
  icon: React.ReactNode;
  onClick?: () => void;
}

/**
 * An enabled panel that has nothing to show yet (#469) - e.g. steam_gaming
 * before the first session. Distinct from PanelPlaceholder, which means no
 * panel is enabled at all and points the admin to the Plugins page.
 */
export const PanelEmpty: React.FC<PanelEmptyProps> = ({ title, icon, onClick }) => {
  const { t } = useTranslation('dashboard');

  return (
    <div
      onClick={onClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 ${onClick ? 'cursor-pointer active:scale-[0.98] touch-manipulation' : ''}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
          <p className="mt-2 text-lg font-medium text-slate-500">
            {t('pluginPanel.noData', 'No data yet')}
          </p>
        </div>
        <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
          {icon}
        </div>
      </div>
    </div>
  );
};
