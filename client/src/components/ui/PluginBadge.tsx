import { useTranslation } from 'react-i18next';

interface PluginBadgeProps {
  pluginName?: string;
  size?: 'sm' | 'md';
  className?: string;
}

export function PluginBadge({ pluginName, size = 'sm', className }: PluginBadgeProps) {
  const { t } = useTranslation('system');
  const tooltip = pluginName
    ? t('badges.pluginProvidedBy', { name: pluginName })
    : undefined;

  return (
    <span
      title={tooltip}
      className={`inline-flex items-center rounded-full bg-purple-500/15 border border-purple-500/40 text-purple-300 font-medium ${
        size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-xs'
      } ${className ?? ''}`}
    >
      Plugin
    </span>
  );
}
