import { useTranslation } from 'react-i18next';
import type { SmartDevice } from '../../api/smart';
import { formatBytes } from '../../lib/formatters';

interface SmartDeviceCardProps {
  device: SmartDevice;
  usedBytes: number;
  usagePercent: number;
}

export function SmartDeviceCard({ device, usedBytes, usagePercent }: SmartDeviceCardProps) {
  const { t } = useTranslation('dashboard');

  const criticalAttributes = device.attributes.filter(attr =>
    ['Reallocated_Sector_Ct', 'Current_Pending_Sector', 'Uncorrectable_Error_Cnt'].includes(attr.name)
  );
  const tempAttr = device.attributes.find(attr => attr.name === 'Temperature_Celsius');

  const circleStyle = {
    backgroundImage: `conic-gradient(#0ea5e9 ${Math.min(usagePercent, 100) * 3.6}deg, rgba(15,23,42,0.8) ${Math.min(usagePercent, 100) * 3.6}deg)`
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-sky-500/30">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950/70">
              <svg className="h-5 w-5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 3.75H6.912a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H15" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-slate-100">{device.model}</p>
              <p className="text-xs text-slate-500">{device.name} • {device.serial}</p>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="text-slate-500">{t('smart.device.status')}</p>
              <p className={`mt-1 font-medium ${device.status === 'PASSED' ? 'text-emerald-300' : device.status === 'UNKNOWN' ? 'text-amber-300' : 'text-rose-300'}`}>
                {device.status}
              </p>
            </div>
            <div>
              <p className="text-slate-500">{t('smart.device.capacity')}</p>
              <p className="mt-1 font-medium text-slate-200">
                {device.capacity_bytes ? formatBytes(device.capacity_bytes) : 'N/A'}
              </p>
            </div>
            <div>
              <p className="text-slate-500">{t('smart.device.temperature')}</p>
              <p className="mt-1 font-medium text-slate-200">
                {device.temperature !== null ? `${device.temperature}°C` : tempAttr ? `${tempAttr.raw}°C` : 'N/A'}
              </p>
            </div>
            {criticalAttributes.slice(0, 1).map(attr => (
              <div key={attr.id}>
                <p className="text-slate-500">{attr.name.replace(/_/g, ' ')}</p>
                <p className={`mt-1 font-medium ${attr.status === 'OK' ? 'text-emerald-300' : 'text-rose-300'}`}>
                  {attr.raw} ({attr.status})
                </p>
              </div>
            ))}
          </div>
        </div>
        <div className="flex flex-col items-center justify-center flex-shrink-0">
          <div className="relative flex h-16 w-16 sm:h-20 sm:w-20 items-center justify-center">
            <div className="glow-ring h-16 w-16 sm:h-20 sm:w-20">
              <div className="absolute inset-1 rounded-full border border-slate-900/80 bg-slate-950/80" />
              <div className="glow-ring h-12 w-12 sm:h-16 sm:w-16 border-none" style={circleStyle}>
                <div className="h-8 w-8 sm:h-12 sm:w-12 rounded-full bg-slate-950/90" />
              </div>
            </div>
            <div className="absolute text-center">
              <p className="text-sm sm:text-base font-semibold text-white">{Math.round(usagePercent)}%</p>
              <p className="text-[0.5rem] sm:text-[0.55rem] text-slate-400">{formatBytes(usedBytes)}</p>
            </div>
          </div>
          <p className="mt-1 text-[0.65rem] text-slate-500">{t('smart.device.used')}</p>
        </div>
      </div>
    </div>
  );
}
