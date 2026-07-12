import { useTranslation } from 'react-i18next';
import { formatNumber } from '../../../lib/formatters';
import type { ChartDataPoint } from '../../../hooks/useFanCurveInteraction';

interface FanCurveTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: ChartDataPoint }>;
}

export default function FanCurveTooltip({ active, payload }: FanCurveTooltipProps) {
  const { t } = useTranslation(['system', 'common']);

  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0].payload as ChartDataPoint;

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs text-slate-400">
        {data.isCurrentPoint ? t('system:fanControl.curve.current') : t('system:fanControl.curve.curvePoint')}
      </p>
      <p className="text-sm font-semibold text-white">
        {formatNumber(data.temp, 1)}°C → {data.pwm}%
      </p>
    </div>
  );
}
