import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Pencil, X, Plus, Cpu, MonitorSmartphone, HardDrive, Sigma, ChevronDown, ChevronRight } from 'lucide-react';
import {
  renameSensor, clearSensorLabel,
  deleteComposite,
} from '../../api/fan-control';
import type { TempSensorInfo, CompositeSensorInfo } from '../../api/fan-control';
import { handleApiError } from '../../lib/errorHandling';
import CompositeSensorModal from './CompositeSensorModal';

const KIND_ICONS = {
  hwmon: Cpu,
  gpu: MonitorSmartphone,
  disk: HardDrive,
  mix: Sigma,
} as const;

// A sensor is considered inactive when it reports exactly 0.0°C — those are
// almost always disconnected motherboard inputs (PCH_*, etc.) that clutter
// the panel without conveying useful information.
const isInactive = (s: TempSensorInfo): boolean => s.current_temp === 0;

interface SensorsPanelProps {
  sensors: TempSensorInfo[];
  composites: CompositeSensorInfo[];
  onReload: () => void;
}

export default function SensorsPanel({ sensors, composites, onReload }: SensorsPanelProps) {
  const { t } = useTranslation(['system', 'common']);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [showInactive, setShowInactive] = useState(false);

  const { activeSensors, inactiveSensors } = useMemo(() => {
    const active: TempSensorInfo[] = [];
    const inactive: TempSensorInfo[] = [];
    for (const s of sensors) {
      (isInactive(s) ? inactive : active).push(s);
    }
    return { activeSensors: active, inactiveSensors: inactive };
  }, [sensors]);

  const saveLabel = async (sensorId: string) => {
    if (!editLabel.trim()) {
      setEditingId(null);
      return;
    }
    try {
      await renameSensor(sensorId, editLabel.trim());
      toast.success(t('system:fanControl.sensors.renamed'));
      setEditingId(null);
      onReload();
    } catch (err) {
      handleApiError(err, t('system:fanControl.sensors.renameFailed'));
    }
  };

  const renderSensor = (s: TempSensorInfo) => {
    const Icon = KIND_ICONS[s.kind] ?? Cpu;
    const display = s.custom_label || s.label || s.device_name;
    const isEditing = editingId === s.sensor_id;
    // When a custom label is set, surface the original kernel label as the
    // subtitle (instead of the sensor_id) so users can tell what they
    // renamed and don't confuse "Composite"-labeled sensors with mix sensors.
    const subtitle = s.custom_label
      ? `${s.label || s.device_name} · ${s.sensor_id}`
      : s.sensor_id;

    return (
      <div key={s.sensor_id} className="flex items-center gap-2 p-2 border border-slate-700/50 rounded-lg bg-slate-800/40">
        <Icon size={16} className="text-slate-400 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <input
              value={editLabel}
              onChange={(e) => setEditLabel(e.target.value)}
              onBlur={() => saveLabel(s.sensor_id)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveLabel(s.sensor_id); }}
              autoFocus
              className="w-full bg-slate-900 border border-slate-600 rounded px-1 text-sm text-white"
            />
          ) : (
            <div className="text-sm font-medium text-white truncate">{display}</div>
          )}
          <div className="text-xs text-slate-400 truncate">{subtitle}</div>
        </div>
        <div className="text-sm tabular-nums text-white flex-shrink-0">
          {s.current_temp != null ? `${s.current_temp.toFixed(1)}°C` : '—'}
        </div>
        {!isEditing && (
          <button
            onClick={() => { setEditingId(s.sensor_id); setEditLabel(s.custom_label ?? ''); }}
            className="p-1 text-slate-400 hover:text-white transition-colors"
            title={t('common:rename')}
          >
            <Pencil size={14} />
          </button>
        )}
        {s.custom_label && !isEditing && (
          <button
            onClick={async () => {
              try {
                await clearSensorLabel(s.sensor_id);
                onReload();
              } catch (err) {
                handleApiError(err, t('system:fanControl.sensors.resetFailed'));
              }
            }}
            className="p-1 text-slate-400 hover:text-rose-400 transition-colors"
            title={t('common:reset')}
          >
            <X size={14} />
          </button>
        )}
      </div>
    );
  };

  return (
    <div className="card border-slate-800/50 bg-slate-900/55 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-white">{t('system:fanControl.sensors.title')}</h3>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1 px-2 py-1 text-xs bg-sky-500 text-white rounded-lg hover:bg-sky-400 transition-colors"
        >
          <Plus size={14} /> {t('system:fanControl.sensors.addComposite')}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {activeSensors.map(renderSensor)}
      </div>

      {inactiveSensors.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setShowInactive((v) => !v)}
            className="mt-3 flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            {showInactive ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {t('system:fanControl.sensors.inactive', { count: inactiveSensors.length })}
          </button>
          {showInactive && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2 opacity-60">
              {inactiveSensors.map(renderSensor)}
            </div>
          )}
        </>
      )}

      {composites.length > 0 && (
        <>
          <h4 className="font-medium mt-4 mb-2 text-sm text-white">{t('system:fanControl.sensors.compositeTitle')}</h4>
          <div className="space-y-2">
            {composites.map((c) => (
              <div key={c.id} className="flex items-center gap-2 p-2 border border-slate-700/50 rounded-lg bg-slate-800/40">
                <Sigma size={16} className="text-sky-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white">{c.name}</div>
                  <div className="text-xs text-slate-400">
                    {t(`system:fanControl.sensors.functions.${c.function}`)} · {c.source_ids.length} {t('system:fanControl.sensors.sources')}
                  </div>
                </div>
                <div className="text-sm tabular-nums text-white flex-shrink-0">
                  {c.current_temp != null ? `${c.current_temp.toFixed(1)}°C` : '—'}
                </div>
                <button
                  onClick={async () => {
                    try {
                      await deleteComposite(c.id);
                      onReload();
                    } catch (err) {
                      handleApiError(err, t('system:fanControl.sensors.deleteFailed'));
                    }
                  }}
                  className="p-1 text-slate-400 hover:text-rose-400 transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {showModal && (
        <CompositeSensorModal
          availableSensors={sensors}
          onClose={() => setShowModal(false)}
          onCreated={() => { setShowModal(false); onReload(); }}
        />
      )}
    </div>
  );
}
