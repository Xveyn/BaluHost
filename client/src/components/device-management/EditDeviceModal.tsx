import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../ui/Modal';
import type { Device } from '../../api/devices';

const PLATFORM_LABELS: Record<string, string> = {
  ios: 'iOS',
  android: 'Android',
  windows: 'Windows',
  mac: 'macOS',
  linux: 'Linux',
  unknown: 'Desktop',
};

interface EditDeviceModalProps {
  device: Device | null;
  onClose: () => void;
  onSave: (device: Device, newName: string) => Promise<boolean>;
}

export function EditDeviceModal({ device, onClose, onSave }: EditDeviceModalProps) {
  const { t } = useTranslation(['devices']);
  const [newDeviceName, setNewDeviceName] = useState('');

  useEffect(() => {
    if (device) setNewDeviceName(device.name);
  }, [device]);

  const handleSave = async () => {
    if (!device) return;
    const ok = await onSave(device, newDeviceName);
    if (ok) onClose();
  };

  return (
    <Modal isOpen={!!device} onClose={onClose} title={t('modal.editTitle')}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">
            {t('fields.deviceName')}
          </label>
          <input
            type="text"
            value={newDeviceName}
            onChange={(e) => setNewDeviceName(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            placeholder={t('register.deviceNamePlaceholder')}
          />
        </div>

        {device && (
          <div className="text-xs text-slate-500">
            <p>{t('fields.type')}: {device.type === 'mobile' ? t('stats.mobile') : t('stats.desktop')}</p>
            <p>{t('fields.platform')}: {PLATFORM_LABELS[device.platform] || device.platform}</p>
          </div>
        )}
      </div>

      <div className="mt-6 flex gap-2">
        <button
          onClick={onClose}
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 touch-manipulation active:scale-95"
        >
          {t('buttons.cancel')}
        </button>
        <button
          onClick={handleSave}
          className="flex-1 rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/20 touch-manipulation active:scale-95"
        >
          {t('buttons.save')}
        </button>
      </div>
    </Modal>
  );
}
