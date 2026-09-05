import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Cpu } from 'lucide-react';
import { setGpuManualMode } from '../../api/fan-control';
import { handleApiError } from '../../lib/errorHandling';

interface Props {
  fanId: string;
}

export default function FirmwareFanNotice({ fanId }: Props) {
  const { t } = useTranslation(['system']);
  const [busy, setBusy] = useState(false);

  // Der 400er-Guard auf gpu-manual-mode greift bewusst nur bei enable=true,
  // damit ein Luefter, der einmal in den manuellen Modus geschaltet wurde,
  // immer wieder herauskommt. Dieser Button ist der einzige UI-Weg dorthin —
  // ohne ihn waere der Ausschalt-Pfad nur noch per curl erreichbar. Ein Aufruf
  // auf einem Luefter, der nie manuell war, ist harmlos (stellt auto/pwm_enable=2
  // wieder her, also genau den gewuenschten Zustand).
  const resetManualMode = async () => {
    setBusy(true);
    try {
      await setGpuManualMode(fanId, false);
      toast.success(t('system:fanControl.gpu.firmware.resetSuccess'));
    } catch (err) {
      handleApiError(err, t('system:fanControl.gpu.firmware.resetButton'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-sky-500/30 bg-sky-500/5 rounded p-3">
      <div className="flex items-start gap-2">
        <Cpu size={16} className="text-sky-400 mt-0.5" />
        <div className="flex-1">
          <div className="text-sm font-medium text-white">
            {t('system:fanControl.gpu.firmware.title')}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {t('system:fanControl.gpu.firmware.explanation')}
          </div>
          <button
            onClick={resetManualMode}
            disabled={busy}
            className="mt-2 px-3 py-1 text-xs rounded bg-slate-700 text-slate-200 hover:bg-slate-600 disabled:opacity-50"
          >
            {t('system:fanControl.gpu.firmware.resetButton')}
          </button>
        </div>
      </div>
    </div>
  );
}
