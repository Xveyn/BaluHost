import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Modal } from '../ui/Modal';
import { createComposite } from '../../api/fan-control';
import type { TempSensorInfo } from '../../api/fan-control';
import { handleApiError } from '../../lib/errorHandling';

interface Props {
  availableSensors: TempSensorInfo[];
  onClose: () => void;
  onCreated: () => void;
}

export default function CompositeSensorModal({ availableSensors, onClose, onCreated }: Props) {
  const { t } = useTranslation(['system', 'common']);
  const [name, setName] = useState('');
  const [fn, setFn] = useState<'max' | 'min' | 'avg'>('max');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const submit = async () => {
    if (!name.trim() || selected.size < 2) return;
    setSubmitting(true);
    try {
      await createComposite({ name: name.trim(), function: fn, source_ids: Array.from(selected) });
      toast.success(t('system:fanControl.sensors.compositeCreated'));
      onCreated();
    } catch (err) {
      handleApiError(err, t('system:fanControl.sensors.createFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen onClose={onClose} title={t('system:fanControl.sensors.createComposite')}>
      <div className="space-y-4">
        <div>
          <label className="text-sm font-medium text-slate-300 block mb-1">{t('common:name')}</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-white text-sm focus:outline-none focus:border-sky-500"
          />
        </div>
        <div>
          <label className="text-sm font-medium text-slate-300 block mb-1">{t('system:fanControl.sensors.function')}</label>
          <div className="flex gap-2 mt-1">
            {(['max', 'min', 'avg'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFn(f)}
                className={`px-3 py-1 rounded-lg text-sm transition-colors ${
                  fn === f
                    ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {t(`system:fanControl.sensors.functions.${f}`)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-sm font-medium text-slate-300 block mb-1">{t('system:fanControl.sensors.sources')}</label>
          <div className="max-h-60 overflow-y-auto border border-slate-700 rounded-lg p-2 space-y-1 bg-slate-900/50">
            {availableSensors.filter((s) => s.kind !== 'mix').map((s) => (
              <label key={s.sensor_id} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-slate-800/60 rounded px-1 py-0.5">
                <input
                  type="checkbox"
                  checked={selected.has(s.sensor_id)}
                  onChange={() => toggle(s.sensor_id)}
                  className="accent-sky-500"
                />
                <span className="flex-1 truncate text-white">{s.custom_label || s.label || s.device_name}</span>
                <span className="text-xs text-slate-400">{s.kind}</span>
              </label>
            ))}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {selected.size}/6 {t('system:fanControl.sensors.selected')}
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg bg-slate-700 text-slate-300 hover:bg-slate-600 text-sm transition-colors"
          >
            {t('common:cancel')}
          </button>
          <button
            onClick={submit}
            disabled={!name.trim() || selected.size < 2 || selected.size > 6 || submitting}
            className="px-3 py-1.5 rounded-lg bg-sky-500 text-white hover:bg-sky-400 disabled:opacity-50 disabled:cursor-not-allowed text-sm transition-colors shadow-lg shadow-sky-500/20"
          >
            {t('common:create')}
          </button>
        </div>
      </div>
    </Modal>
  );
}
