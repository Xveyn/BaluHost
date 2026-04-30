import { useTranslation } from 'react-i18next';
import type {
  AmdProfileMode,
  AmdStateConfig,
  GpuPowerCapabilities,
  GpuPowerConfig,
  NvidiaStateConfig,
} from '../../types/gpuPower';

interface Props {
  value: GpuPowerConfig;
  caps: GpuPowerCapabilities | null;
  onChange: (next: GpuPowerConfig) => void;
  disabled?: boolean;
}

const STATE_KEYS = ['active', 'standby', 'deep_idle'] as const;
type StateKey = (typeof STATE_KEYS)[number];

const SELECT_CLASS =
  'rounded-lg border border-slate-700/50 bg-slate-900/60 px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500/40 disabled:opacity-50';

const INPUT_CLASS =
  'w-full rounded-lg border border-slate-700/50 bg-slate-900/60 px-2 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-emerald-500/40 disabled:opacity-50';

export function GpuPowerHardware({ value, caps, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);

  if (!caps || caps.vendor === null) {
    return (
      <p className="text-xs text-slate-500">{t('system:power.gpu.hardware.noVendor')}</p>
    );
  }

  if (caps.vendor === 'amd' || caps.vendor === 'dev') {
    return <AmdSection value={value} caps={caps} onChange={onChange} disabled={disabled} />;
  }

  if (caps.vendor === 'nvidia') {
    return <NvidiaSection value={value} caps={caps} onChange={onChange} disabled={disabled} />;
  }

  return null;
}

function AmdSection({ value, caps, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);

  const setField = (state: StateKey, patch: Partial<AmdStateConfig>) => {
    const key = `amd_${state}` as const;
    onChange({ ...value, [key]: { ...value[key], ...patch } });
  };

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium text-slate-200">
        {t('system:power.gpu.hardware.amdHeading')}
      </h4>
      <div className="grid grid-cols-3 gap-2 items-center text-[10px] sm:text-xs uppercase tracking-wide text-slate-500">
        <span>{t('system:power.gpu.hardware.columns.state')}</span>
        <span>{t('system:power.gpu.hardware.columns.performance')}</span>
        <span>{t('system:power.gpu.hardware.columns.profile')}</span>
      </div>
      {STATE_KEYS.map((key) => {
        const sc = value[`amd_${key}`];
        return (
          <div key={key} className="grid grid-cols-3 gap-2 items-center">
            <span className="text-sm text-slate-300">{t(`system:power.gpu.states.${key}`)}</span>
            <select
              disabled={disabled}
              value={sc.performance_level ?? ''}
              onChange={(e) =>
                setField(key, { performance_level: e.target.value || null })
              }
              className={SELECT_CLASS}
            >
              <option value="">{t('system:power.gpu.hardware.unset')}</option>
              {caps?.amd_performance_levels.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <select
              disabled={disabled}
              value={sc.profile_mode ?? ''}
              onChange={(e) =>
                setField(key, {
                  profile_mode: (e.target.value || null) as AmdProfileMode | null,
                })
              }
              className={SELECT_CLASS}
            >
              <option value="">{t('system:power.gpu.hardware.unset')}</option>
              {caps?.amd_profile_modes.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        );
      })}
    </div>
  );
}

function NvidiaSection({ value, caps, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);

  const setField = (state: StateKey, patch: Partial<NvidiaStateConfig>) => {
    const key = `nvidia_${state}` as const;
    onChange({ ...value, [key]: { ...value[key], ...patch } });
  };

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h4 className="text-sm font-medium text-slate-200">
          {t('system:power.gpu.hardware.nvidiaHeading')}
        </h4>
        <span className="text-xs text-slate-500">
          {caps?.nvidia_min_clock_mhz ?? '?'}–{caps?.nvidia_max_clock_mhz ?? '?'} MHz
          {caps?.nvidia_min_power_watts != null && caps?.nvidia_max_power_watts != null && (
            <> &bull; {caps.nvidia_min_power_watts}–{caps.nvidia_max_power_watts} W</>
          )}
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2 items-center text-[10px] sm:text-xs uppercase tracking-wide text-slate-500">
        <span>{t('system:power.gpu.hardware.columns.state')}</span>
        <span>{t('system:power.gpu.hardware.minMhz')}</span>
        <span>{t('system:power.gpu.hardware.maxMhz')}</span>
        <span>{t('system:power.gpu.hardware.powerW')}</span>
      </div>
      {STATE_KEYS.map((key) => {
        const sc = value[`nvidia_${key}`];
        return (
          <div key={key} className="grid grid-cols-4 gap-2 items-center">
            <span className="text-sm text-slate-300">{t(`system:power.gpu.states.${key}`)}</span>
            <input
              type="number"
              placeholder={t('system:power.gpu.hardware.minMhz')}
              disabled={disabled}
              value={sc.min_clock_mhz ?? ''}
              onChange={(e) =>
                setField(key, {
                  min_clock_mhz: e.target.value === '' ? null : Number(e.target.value),
                })
              }
              className={INPUT_CLASS}
            />
            <input
              type="number"
              placeholder={t('system:power.gpu.hardware.maxMhz')}
              disabled={disabled}
              value={sc.max_clock_mhz ?? ''}
              onChange={(e) =>
                setField(key, {
                  max_clock_mhz: e.target.value === '' ? null : Number(e.target.value),
                })
              }
              className={INPUT_CLASS}
            />
            <input
              type="number"
              placeholder={t('system:power.gpu.hardware.powerW')}
              disabled={disabled}
              value={sc.power_limit_watts ?? ''}
              onChange={(e) =>
                setField(key, {
                  power_limit_watts: e.target.value === '' ? null : Number(e.target.value),
                })
              }
              className={INPUT_CLASS}
            />
          </div>
        );
      })}
    </div>
  );
}
