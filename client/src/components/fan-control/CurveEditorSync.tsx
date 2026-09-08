import { useTranslation } from 'react-i18next';
import type { FanInfo } from '../../api/fan-control';

interface Props {
  allFans: FanInfo[];
  currentFanId: string;
  syncFanId: string | null;
  onChange: (v: string | null) => void;
  disabled?: boolean;
}

/**
 * Wer den Kanal gerade vorgibt, sofern es nicht BaluHost ist (#582).
 *
 * Ausgeblendet werden diese Luefter bewusst NICHT: eine bestehende
 * Sync-Kurve, deren Quelle gerade freigegeben wurde, verschwaende dann aus
 * der Liste, und das Feld zeigte einen leeren Wert bei intakter
 * Konfiguration. Sichtbar und beschriftet ist ehrlicher als weg.
 *
 * Die beiden Zustaende sind auseinandergehalten, weil sie verschiedene Dinge
 * bedeuten: bei `released` gibt die Board-Automatik einen lebenden Wert vor,
 * bei `abandoned` regelt niemand -- der Wert steht seit der Freigabe still,
 * und eine Sync-Kurve darauf friert mit ein.
 */
function quellHinweis(fan: FanInfo, t: (k: string) => string): string | null {
  if (fan.ownership === 'released') return t('system:fanControl.curveTypes.sourceReleased');
  if (fan.ownership === 'abandoned') return t('system:fanControl.curveTypes.sourceAbandoned');
  return null;
}

export default function CurveEditorSync({ allFans, currentFanId, syncFanId, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-400">{t('system:fanControl.curveTypes.syncDescription')}</p>
      <select
        value={syncFanId ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={disabled}
        className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white"
      >
        <option value="">{t('system:fanControl.curveTypes.selectFan')}</option>
        {allFans
          .filter((f) => f.fan_id !== currentFanId)
          // Bleibt eine Ausblendung, anders als die Freigabe darunter: eine
          // firmware-verwaltete Karte regelt BaluHost dauerhaft nicht (#480),
          // die Option waere eine Quelle, die es nie geben wird.
          .filter((f) => f.pwm_control !== 'firmware_managed')
          .map((f) => {
            const hinweis = quellHinweis(f, t);
            return (
              <option key={f.fan_id} value={f.fan_id}>
                {hinweis ? `${f.name} — ${hinweis}` : f.name}
              </option>
            );
          })}
      </select>
    </div>
  );
}
