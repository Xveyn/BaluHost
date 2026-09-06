import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Cpu } from 'lucide-react';
import {
  setGpuManualMode,
  getGpuAcoustics,
  setGpuAcoustics,
  type GpuAcousticsStatus,
} from '../../api/fan-control';
import { handleApiError } from '../../lib/errorHandling';

interface Props {
  fanId: string;
}

export default function FirmwareFanNotice({ fanId }: Props) {
  const { t } = useTranslation(['system']);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<GpuAcousticsStatus | null>(null);
  const [draft, setDraft] = useState<Record<string, number>>({});

  useEffect(() => {
    getGpuAcoustics()
      .then((s) => {
        setStatus(s);
        setDraft(Object.fromEntries(
          Object.entries(s.nodes).map(([k, n]) => [k, n.desired ?? n.current]),
        ));
      })
      .catch((err) => handleApiError(err, t('system:fanControl.gpu.acoustics.title')));
    // Fetch once per fan, not on every render: `t` is only used inside the
    // catch handler and including it here would re-trigger the fetch on
    // every render whose i18n instance hands back a fresh `t` reference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fanId]);

  const applyAcoustics = async (values: Record<string, number | null>) => {
    try {
      const next = await setGpuAcoustics(values);
      setStatus(next);
    } catch (err) {
      handleApiError(err, t('system:fanControl.gpu.acoustics.title'));
    }
  };

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

          {status?.available && (
            <div className="mt-3 space-y-3">
              <div className="text-sm font-medium text-white">
                {t('system:fanControl.gpu.acoustics.title')}
              </div>

              {Object.entries(status.nodes).map(([name, node]) => (
                <label key={name} className="block">
                  <span className="text-xs text-slate-400">
                    {t(`system:fanControl.gpu.acoustics.${name}`)}: {draft[name]}
                  </span>
                  <input
                    type="range"
                    aria-label={name}
                    min={node.minimum}
                    max={node.maximum}
                    value={draft[name]}
                    onChange={(e) =>
                      setDraft({ ...draft, [name]: parseInt(e.target.value, 10) })}
                    className="w-full"
                  />
                </label>
              ))}

              <p data-testid="gpu-acoustics-zero-rpm-hint" className="text-xs text-slate-400">
                {t('system:fanControl.gpu.acoustics.hint')}
              </p>
              <p className="text-xs text-slate-400">
                {t('system:fanControl.gpu.acoustics.curveWarning')}
              </p>
              {status.competing_manager && (
                <p data-testid="gpu-acoustics-competing" className="text-xs text-amber-400">
                  {t('system:fanControl.gpu.acoustics.competing')}
                </p>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => applyAcoustics(draft)}
                  className="px-3 py-1 text-sm rounded bg-sky-500 text-white"
                >
                  {t('system:fanControl.gpu.acoustics.save')}
                </button>
                <button
                  onClick={() => applyAcoustics(Object.fromEntries(
                    Object.keys(status.nodes).map((k) => [k, null])))}
                  className="px-3 py-1 text-sm rounded bg-slate-700 text-slate-200"
                >
                  {t('system:fanControl.gpu.acoustics.reset')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
