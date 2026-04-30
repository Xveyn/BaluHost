// client/src/components/dashboard/panels/PanelPlaceholder.tsx
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Plug } from 'lucide-react';
import { useAuth } from '../../../contexts/AuthContext';

export const PanelPlaceholder: React.FC = () => {
  const { t } = useTranslation('dashboard');
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  return (
    <div
      onClick={isAdmin ? () => navigate('/plugins') : undefined}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(56,189,248,0.15)] ${isAdmin ? 'cursor-pointer active:scale-[0.98] touch-manipulation' : ''}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">
            {t('pluginPanel.title', 'Plugin Panel')}
          </p>
          <p className="mt-2 text-lg font-medium text-slate-500">
            {t('pluginPanel.noPlugin', 'No plugin configured')}
          </p>
        </div>
        <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
          <Plug className="h-6 w-6" />
        </div>
      </div>
      {isAdmin && (
        <div className="mt-3 text-xs text-slate-500">
          {t('pluginPanel.configureHint', 'Enable a plugin\'s Dashboard panel on the Plugins page')}
        </div>
      )}
    </div>
  );
};
