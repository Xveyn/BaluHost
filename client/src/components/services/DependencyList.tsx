import { CheckCircle, XCircle, Terminal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { DependencyStatus } from '../../api/service-status';

interface DependencyListProps {
  dependencies: DependencyStatus[];
}

export default function DependencyList({ dependencies }: DependencyListProps) {
  const { t } = useTranslation(['system', 'common']);
  
  return (
    <div className="card border-slate-800/40">
      <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
        <Terminal className="w-5 h-5 text-slate-400" />
        {t('system:services.dependencies.title')}
      </h3>

      <div className="space-y-3">
        {dependencies.map((dep) => (
          <div
            key={dep.name}
            className={`p-3 rounded-lg border ${
              dep.available
                ? 'border-green-500/20 bg-green-500/5'
                : 'border-red-500/20 bg-red-500/5'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                {dep.available ? (
                  <CheckCircle className="w-4 h-4 text-green-500" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-500" />
                )}
                <span className="font-medium text-white">{dep.name}</span>
              </div>
              <span
                className={`px-2 py-0.5 rounded text-xs font-medium ${
                  dep.available
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-red-500/20 text-red-400'
                }`}
              >
                {dep.available ? t('system:services.dependencies.available') : t('system:services.dependencies.notFound')}
              </span>
            </div>

            {dep.available && dep.path && (
              <p className="text-xs text-slate-400 mb-1 truncate" title={dep.path}>
                {t('system:services.dependencies.path')}: {dep.path}
              </p>
            )}

            {dep.available && dep.version && (
              <p className="text-xs text-slate-400 mb-1 truncate" title={dep.version}>
                {t('system:services.dependencies.version')}: {dep.version}
              </p>
            )}

            {dep.required_for.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {dep.required_for.map((feature) => (
                  <span
                    key={feature}
                    className="px-1.5 py-0.5 bg-slate-700 text-slate-300 rounded text-xs"
                  >
                    {feature}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
