import { Clock } from 'lucide-react';
import { getChannelInfo, type UpdateConfig, type UpdateChannel } from '../../api/updates';

interface UpdateSettingsTabProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  config: UpdateConfig;
  configLoading: boolean;
  onConfigChange: (key: keyof UpdateConfig, value: UpdateConfig[keyof UpdateConfig]) => void;
}

export default function UpdateSettingsTab({
  t,
  config,
  configLoading,
  onConfigChange,
}: UpdateSettingsTabProps) {
  return (
    <div className="bg-slate-800 rounded-lg p-5 border border-slate-700 space-y-6">
      {/* Auto-Check */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-white">{t('settings.autoCheck')}</h3>
          <p className="text-sm text-slate-400">
            {t('settings.autoCheckDesc')}
          </p>
        </div>
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={config.auto_check_enabled}
            onChange={(e) =>
              onConfigChange('auto_check_enabled', e.target.checked)
            }
            disabled={configLoading}
            className="sr-only peer"
          />
          <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
        </label>
      </div>

      {/* Check Interval */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-white">{t('settings.checkInterval')}</h3>
          <p className="text-sm text-slate-400">{t('settings.checkIntervalDesc')}</p>
        </div>
        <select
          value={config.check_interval_hours}
          onChange={(e) =>
            onConfigChange('check_interval_hours', parseInt(e.target.value))
          }
          disabled={configLoading || !config.auto_check_enabled}
          className="bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm"
        >
          <option value={6}>{t('settings.every6Hours')}</option>
          <option value={12}>{t('settings.every12Hours')}</option>
          <option value={24}>{t('settings.every24Hours')}</option>
          <option value={48}>{t('settings.every2Days')}</option>
          <option value={168}>{t('settings.everyWeek')}</option>
        </select>
      </div>

      {/* Update Channel */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-white">{t('settings.channel')}</h3>
          <p className="text-sm text-slate-400">
            {getChannelInfo(config.channel as UpdateChannel).description}
          </p>
        </div>
        <select
          value={config.channel}
          onChange={(e) =>
            onConfigChange('channel', e.target.value as UpdateChannel)
          }
          disabled={configLoading}
          className="bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm"
        >
          <option value="stable">{t('settings.stable')}</option>
          <option value="unstable">{t('settings.unstable')}</option>
        </select>
      </div>

      {/* Auto Backup */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-white">{t('settings.autoBackup')}</h3>
          <p className="text-sm text-slate-400">
            {t('settings.autoBackupDesc')}
          </p>
        </div>
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={config.auto_backup_before_update}
            onChange={(e) =>
              onConfigChange('auto_backup_before_update', e.target.checked)
            }
            disabled={configLoading}
            className="sr-only peer"
          />
          <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
        </label>
      </div>

      {/* Require Healthy Services */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-white">{t('settings.requireHealthy')}</h3>
          <p className="text-sm text-slate-400">
            {t('settings.requireHealthyDesc')}
          </p>
        </div>
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={config.require_healthy_services}
            onChange={(e) =>
              onConfigChange('require_healthy_services', e.target.checked)
            }
            disabled={configLoading}
            className="sr-only peer"
          />
          <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
        </label>
      </div>

      {/* Last Check Info */}
      {config.last_check_at && (
        <div className="pt-4 border-t border-slate-700">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Clock className="h-4 w-4" />
            <span>
              {t('version.lastChecked')} {new Date(config.last_check_at).toLocaleString()}
            </span>
            {config.last_available_version && (
              <span className="text-blue-400">
                (v{config.last_available_version} available)
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
