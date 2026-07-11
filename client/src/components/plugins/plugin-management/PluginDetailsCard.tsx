import { useTranslation } from 'react-i18next';
import { ExternalLink } from 'lucide-react';
import type { PluginDetail } from '../../../api/plugins';
import { safeExternalUrl } from '../../../lib/safeUrl';
import { resolvePluginString } from '../../../lib/pluginI18n';

export function PluginDetailsCard({ plugin }: { plugin: PluginDetail }) {
  const { t } = useTranslation(['plugins', 'common']);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h3 className="text-lg font-medium text-white mb-4">
        {resolvePluginString(plugin.translations, 'display_name', plugin.display_name)}
      </h3>
      <dl className="space-y-3 text-sm">
        <div className="flex justify-between">
          <dt className="text-slate-500">{t('details.version')}</dt>
          <dd className="text-white">{plugin.version}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">{t('details.author')}</dt>
          <dd className="text-white">{plugin.author}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">{t('details.category')}</dt>
          <dd className="text-white capitalize">{plugin.category}</dd>
        </div>
        {safeExternalUrl(plugin.homepage) && (
          <div className="flex justify-between">
            <dt className="text-slate-500">{t('details.homepage')}</dt>
            <dd>
              <a
                href={safeExternalUrl(plugin.homepage)!}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:underline flex items-center gap-1"
              >
                {t('details.link')} <ExternalLink className="h-3 w-3" />
              </a>
            </dd>
          </div>
        )}
        <div className="flex justify-between">
          <dt className="text-slate-500">{t('details.status')}</dt>
          <dd className={plugin.is_enabled ? 'text-green-400' : 'text-slate-400'}>
            {plugin.is_enabled ? t('status.enabled') : t('status.disabled')}
          </dd>
        </div>
        {plugin.installed_at && (
          <div className="flex justify-between">
            <dt className="text-slate-500">{t('details.installed')}</dt>
            <dd className="text-white">
              {new Date(plugin.installed_at).toLocaleDateString()}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}
