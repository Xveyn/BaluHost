import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Settings, Info, Save, Check } from 'lucide-react';
import toast from 'react-hot-toast';
import { updatePluginConfig } from '../../api/plugins';
import { smartDevicesApi } from '../../api/smart-devices';

interface PluginSettingsSectionProps {
  pluginName: string;
  configSchema: Record<string, any>;
  config: Record<string, any>;
  translations?: Record<string, Record<string, string>>;
}

export function PluginSettingsSection({ pluginName, configSchema, config, translations }: PluginSettingsSectionProps) {
  const { t, i18n } = useTranslation('plugins');
  const [formData, setFormData] = useState<Record<string, any>>(config);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [deviceOptions, setDeviceOptions] = useState<{id: number, name: string}[]>([]);

  const lang = i18n.language?.startsWith('de') ? 'de' : 'en';
  const pluginT = translations?.[lang] ?? translations?.['en'] ?? {};

  // Fetch device options for x-options-source fields
  useEffect(() => {
    const props = configSchema?.properties ?? {};
    const needsDevices = Object.values(props).some(
      (p: any) => p['x-options-source'] === 'smart-devices'
    );
    if (needsDevices) {
      smartDevicesApi.list().then(res => {
        const devices = (res.data.devices ?? [])
          .filter((d: any) => d.plugin_name === pluginName && d.is_active);
        setDeviceOptions(devices.map((d: any) => ({ id: d.id, name: d.name })));
      }).catch(() => {});
    }
  }, [pluginName, configSchema]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updatePluginConfig(pluginName, formData);
      setSaved(true);
      toast.success(t('settings.saved'));
      setTimeout(() => setSaved(false), 2000);
    } catch {
      toast.error(t('settings.saveError'));
    } finally {
      setSaving(false);
    }
  };

  const properties = configSchema?.properties ?? {};
  if (Object.keys(properties).length === 0) return null;

  return (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700/50 p-4 space-y-4">
      <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
        <Settings className="h-4 w-4 text-gray-400" />
        {t('settings.title')}
      </div>

      {Object.entries(properties).map(([key, schema]: [string, any]) => {
        const label = pluginT[`settings_${key}`] ?? schema.title ?? key;

        if (schema.type === 'array' && schema['x-options-source'] === 'smart-devices') {
          const selected: number[] = formData[key] ?? [];
          return (
            <div key={key} className="space-y-1.5">
              <label className="text-sm text-gray-300">{label}</label>
              <div className="space-y-1">
                {deviceOptions.map(dev => (
                  <label key={dev.id} className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer hover:text-gray-300">
                    <input
                      type="checkbox"
                      checked={selected.includes(dev.id)}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...selected, dev.id]
                          : selected.filter(id => id !== dev.id);
                        setFormData({ ...formData, [key]: next });
                      }}
                      className="rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500/20"
                    />
                    {dev.name}
                  </label>
                ))}
                {selected.filter(id => !deviceOptions.some(d => d.id === id)).map(id => (
                  <span key={id} className="text-xs text-gray-500">(Deleted device #{id})</span>
                ))}
                {deviceOptions.length === 0 && (
                  <p className="text-xs text-gray-500">No devices available</p>
                )}
              </div>
            </div>
          );
        }

        if (schema.type === 'boolean') {
          return (
            <label key={key} className="flex items-center justify-between text-sm text-gray-300 cursor-pointer">
              {label}
              <input
                type="checkbox"
                checked={!!formData[key]}
                onChange={(e) => setFormData({ ...formData, [key]: e.target.checked })}
                className="rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500/20"
              />
            </label>
          );
        }

        if (schema.type === 'string') {
          return (
            <div key={key} className="space-y-1.5">
              <label className="text-sm text-gray-300">{label}</label>
              <input
                type="text"
                value={formData[key] ?? ''}
                onChange={(e) => setFormData({ ...formData, [key]: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20"
              />
            </div>
          );
        }

        return null;
      })}

      {/* Hints from plugin translations */}
      {pluginT['settings_third_party_hint'] && (
        <div className="flex gap-2 rounded-lg bg-blue-500/10 border border-blue-500/20 p-3 text-xs text-blue-300">
          <Info className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{pluginT['settings_third_party_hint']}</span>
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-3 py-1.5 text-sm font-medium text-white transition-colors"
      >
        {saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
        {saved ? t('settings.saved') : t('settings.save')}
      </button>
    </div>
  );
}
