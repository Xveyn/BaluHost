import { useTranslation } from 'react-i18next';
import { Plug } from 'lucide-react';
import type { PluginInfo } from '../../../api/plugins';
import { PluginListCard } from './PluginListCard';

export function PluginList({
  plugins,
  selectedName,
  actionLoading,
  onSelect,
  onToggle,
}: {
  plugins: PluginInfo[];
  selectedName: string | null;
  actionLoading: boolean;
  onSelect: (name: string) => void;
  onToggle: (plugin: PluginInfo) => void;
}) {
  const { t } = useTranslation(['plugins', 'common']);

  return (
    <div className="lg:col-span-2 space-y-4">
      {plugins.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center">
          <Plug className="h-12 w-12 mx-auto text-slate-600 mb-4" />
          <h3 className="text-lg font-medium text-slate-300 mb-2">{t('empty.noPlugins')}</h3>
          <p className="text-sm text-slate-500">
            {t('empty.noPluginsDesc')}
          </p>
        </div>
      ) : (
        plugins.map((plugin) => (
          <PluginListCard
            key={plugin.name}
            plugin={plugin}
            isSelected={selectedName === plugin.name}
            actionLoading={actionLoading}
            onSelect={onSelect}
            onToggle={onToggle}
          />
        ))
      )}
    </div>
  );
}
