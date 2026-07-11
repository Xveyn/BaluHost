import { useTranslation } from 'react-i18next';
import type { PluginDetail, ScopeInfo } from '../../../api/plugins';

export function ScopeGrantModal({
  plugin,
  scopeCatalog,
  selectedScopes,
  onToggleScope,
  onCancel,
  onConfirm,
}: {
  plugin: PluginDetail;
  scopeCatalog: ScopeInfo[];
  selectedScopes: string[];
  onToggleScope: (scope: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation(['plugins', 'common']);

  const descs = t('scopeDescriptions', { returnObjects: true }) as Record<
    string,
    { label: string; description: string }
  >;
  const requested = (plugin.requested_api_scopes ?? []).filter((s) =>
    scopeCatalog.some((c) => c.key === s),
  );
  const byTier = (tier: 'frontend' | 'backend') =>
    requested
      .map((key) => scopeCatalog.find((c) => c.key === key)!)
      .filter((c) => c.tier === tier);
  const renderScope = (scope: ScopeInfo) => {
    const isChecked = selectedScopes.includes(scope.key);
    const meta = descs?.[scope.key];
    return (
      <label
        key={scope.key}
        className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition ${
          scope.dangerous
            ? 'bg-amber-500/10 border border-amber-500/20'
            : 'bg-slate-800/50 border border-slate-700'
        }`}
      >
        <input
          type="checkbox"
          checked={isChecked}
          onChange={() => onToggleScope(scope.key)}
          className="mt-1 rounded border-slate-600 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-900"
        />
        <div>
          <div className={`text-sm font-medium ${scope.dangerous ? 'text-amber-400' : 'text-white'}`}>
            {meta?.label ?? scope.key}
            {scope.dangerous && (
              <span className="ml-2 text-xs text-amber-500">({t('picker.dangerous')})</span>
            )}
          </div>
          {meta?.description && (
            <p className="text-xs text-slate-500 mt-0.5">{meta.description}</p>
          )}
        </div>
      </label>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
        <h3 className="text-lg font-medium text-white mb-2">
          {t('picker.title', { name: plugin.display_name })}
        </h3>
        <p className="text-sm text-slate-400 mb-4">{t('picker.desc')}</p>
        {requested.length === 0 ? (
          <p className="text-sm text-slate-500 mb-6">{t('picker.noScopes')}</p>
        ) : (
          <div className="space-y-4 mb-6 max-h-72 overflow-y-auto">
            {(['frontend', 'backend'] as const).map((tier) =>
              byTier(tier).length === 0 ? null : (
                <div key={tier} className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {t(`scopeTiers.${tier}`)}
                  </div>
                  {byTier(tier).map(renderScope)}
                </div>
              ),
            )}
          </div>
        )}
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 text-sm font-medium rounded-lg border border-slate-700 text-slate-300 hover:border-slate-600 transition-all touch-manipulation active:scale-95"
          >
            {t('buttons.cancel')}
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 px-4 py-2 text-sm font-medium rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all touch-manipulation active:scale-95"
          >
            {t('picker.grant')}
          </button>
        </div>
      </div>
    </div>
  );
}
