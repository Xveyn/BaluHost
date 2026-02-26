import { useTranslation } from 'react-i18next';
import { Smartphone, Monitor, Edit2, Trash2 } from 'lucide-react';
import { formatRelativeTime } from '../../lib/formatters';
import type { Device } from '../../api/devices';

const PLATFORM_LABELS: Record<string, string> = {
  ios: 'iOS',
  android: 'Android',
  windows: 'Windows',
  mac: 'macOS',
  linux: 'Linux',
  unknown: 'Desktop',
};

interface DeviceCardProps {
  device: Device;
  colorTheme: 'sky' | 'emerald';
  onEdit: (device: Device) => void;
  onDelete?: (device: Device) => void;
}

export function DeviceCard({ device, colorTheme, onEdit, onDelete }: DeviceCardProps) {
  const { t } = useTranslation(['devices', 'common']);
  const icon = device.type === 'mobile'
    ? <Smartphone className="h-5 w-5" />
    : <Monitor className="h-5 w-5" />;

  return (
    <div className={`rounded-2xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-${colorTheme}-500/30`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className={`flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950/70 text-${colorTheme}-400 flex-shrink-0`}>
            {icon}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-100 truncate">{device.name}</p>
            <p className="text-xs text-slate-500">
              {PLATFORM_LABELS[device.platform] || device.platform}
              {device.model && ` • ${device.model}`}
              {device.username && ` • ${device.username}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {device.type === 'mobile' && (
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                device.is_active
                  ? 'border border-green-500/40 bg-green-500/15 text-green-200'
                  : 'border border-slate-700/70 bg-slate-900/70 text-slate-400'
              }`}
            >
              {device.is_active ? t('common:active') : t('common:inactive')}
            </span>
          )}

          <button
            onClick={() => onEdit(device)}
            className={`rounded-lg border border-${colorTheme}-500/30 bg-${colorTheme}-500/10 p-2 text-${colorTheme}-200 transition hover:border-${colorTheme}-500/50 hover:bg-${colorTheme}-500/20`}
            title="Edit device name"
          >
            <Edit2 className="h-4 w-4" />
          </button>

          {onDelete && (
            <button
              onClick={() => onDelete(device)}
              className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
              title="Delete device"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      <div className={`mt-3 grid ${device.type === 'mobile' ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-2 sm:grid-cols-3'} gap-3 text-xs`}>
        {device.type === 'mobile' && (
          <div>
            <p className="text-slate-500">{t('fields.lastSeen')}</p>
            <p className="mt-1 font-medium text-slate-200">{formatRelativeTime(device.last_seen)}</p>
          </div>
        )}
        <div>
          <p className="text-slate-500">{t('fields.lastSync')}</p>
          <p className="mt-1 font-medium text-slate-200">{formatRelativeTime(device.last_sync)}</p>
        </div>
        <div>
          <p className="text-slate-500">{t('fields.registered')}</p>
          <p className="mt-1 font-medium text-slate-200">{formatRelativeTime(device.created_at)}</p>
        </div>
        {device.type === 'mobile' && device.expires_at && (
          <div>
            <p className="text-slate-500">{t('fields.expires')}</p>
            <p className="mt-1 font-medium text-slate-200">{formatRelativeTime(device.expires_at)}</p>
          </div>
        )}
        {device.type === 'desktop' && (
          <div>
            <p className="text-slate-500">{t('fields.status')}</p>
            <p className="mt-1 font-medium text-emerald-300">{t('common:active')}</p>
          </div>
        )}
      </div>
    </div>
  );
}
