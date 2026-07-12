import { useTranslation } from 'react-i18next';
import type { FanCurvePoint } from '../../../api/fan-control';

interface FanCurveTableEditorProps {
  curvePoints: FanCurvePoint[];
  canEdit: boolean;
  minPwm: number;
  maxPwm: number;
  onUpdatePoint: (index: number, field: 'temp' | 'pwm', value: number) => void;
  onRemovePoint: (index: number) => void;
  onAddPoint: () => void;
}

export default function FanCurveTableEditor({
  curvePoints, canEdit, minPwm, maxPwm, onUpdatePoint, onRemovePoint, onAddPoint,
}: FanCurveTableEditorProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full border border-slate-700">
          <thead className="bg-slate-800">
            <tr>
              <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">{t('system:fanControl.details.temperatureCol')}</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">{t('system:fanControl.details.pwmCol')}</th>
              {canEdit && <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">{t('system:fanControl.details.actionsCol')}</th>}
            </tr>
          </thead>
          <tbody>
            {[...curvePoints]
              .map((point, originalIndex) => ({ ...point, originalIndex }))
              .sort((a, b) => a.temp - b.temp)
              .map((point) => (
                <tr key={point.originalIndex} className="border-t border-slate-700">
                  <td className="px-4 py-2">
                    {canEdit ? (
                      <input
                        type="number"
                        value={point.temp}
                        onChange={(e) => onUpdatePoint(point.originalIndex, 'temp', parseFloat(e.target.value))}
                        className="w-20 px-2 py-1 border border-slate-600 rounded bg-slate-800 text-white"
                        min={0}
                        max={150}
                      />
                    ) : (
                      <span className="text-slate-300">{point.temp}°C</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {canEdit ? (
                      <input
                        type="number"
                        value={point.pwm}
                        onChange={(e) => onUpdatePoint(point.originalIndex, 'pwm', parseInt(e.target.value))}
                        className="w-20 px-2 py-1 border border-slate-600 rounded bg-slate-800 text-white"
                        min={minPwm}
                        max={maxPwm}
                      />
                    ) : (
                      <span className="text-slate-300">{point.pwm}%</span>
                    )}
                  </td>
                  {canEdit && (
                    <td className="px-4 py-2">
                      <button
                        onClick={() => onRemovePoint(point.originalIndex)}
                        disabled={curvePoints.length <= 2}
                        className="text-rose-400 hover:text-rose-300 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                      >
                        {t('system:fanControl.curve.remove')}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {canEdit && curvePoints.length < 10 && (
        <button
          onClick={onAddPoint}
          className="mt-3 px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 shadow-lg shadow-sky-500/30 text-sm"
        >
          {t('system:fanControl.curve.addPoint')}
        </button>
      )}
    </>
  );
}
