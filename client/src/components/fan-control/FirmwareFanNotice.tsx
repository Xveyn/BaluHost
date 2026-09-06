import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Cpu } from 'lucide-react';
import {
  setGpuManualMode,
  getGpuAcoustics,
  setGpuAcoustics,
  type GpuAcousticsStatus,
  type GpuAcousticsNode,
} from '../../api/fan-control';
import { handleApiError } from '../../lib/errorHandling';

interface Props {
  fanId: string;
}

// Derive slider positions from the nodes the server reports: the observed
// desired value if BaluHost is managing it, otherwise the card's current
// value. Shared between the initial fetch and every apply/reset response so
// the sliders always reflect what the server actually holds, never a stale
// pre-request draft.
function draftFromNodes(nodes: Record<string, GpuAcousticsNode>): Record<string, number> {
  return Object.fromEntries(
    Object.entries(nodes).map(([k, n]) => [k, n.desired ?? n.current]),
  );
}

export default function FirmwareFanNotice({ fanId }: Props) {
  const { t } = useTranslation(['system']);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<GpuAcousticsStatus | null>(null);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [acousticsBusy, setAcousticsBusy] = useState(false);

  useEffect(() => {
    getGpuAcoustics()
      .then((s) => {
        setStatus(s);
        setDraft(draftFromNodes(s.nodes));
      })
      .catch((err) => handleApiError(err, t('system:fanControl.gpu.acoustics.title')));
    // Fetch once per fan, not on every render: `t` is only used inside the
    // catch handler and including it here would re-trigger the fetch on
    // every render whose i18n instance hands back a fresh `t` reference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fanId]);

  const applyAcoustics = async (
    values: Record<string, number | null>,
    successMessage: string,
  ) => {
    setAcousticsBusy(true);
    try {
      const next = await setGpuAcoustics(values);
      setStatus(next);
      setDraft(draftFromNodes(next.nodes));
      toast.success(successMessage);
    } catch (err) {
      handleApiError(err, t('system:fanControl.gpu.acoustics.title'));
    } finally {
      setAcousticsBusy(false);
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
                  onClick={() => applyAcoustics(
                    draft,
                    t('system:fanControl.gpu.acoustics.saveSuccess'),
                  )}
                  disabled={acousticsBusy}
                  className="px-3 py-1 text-sm rounded bg-sky-500 text-white disabled:opacity-50"
                >
                  {t('system:fanControl.gpu.acoustics.save')}
                </button>
                <button
                  onClick={() => applyAcoustics(
                    Object.fromEntries(Object.keys(status.nodes).map((k) => [k, null])),
                    t('system:fanControl.gpu.acoustics.resetSuccess'),
                  )}
                  disabled={acousticsBusy}
                  className="px-3 py-1 text-sm rounded bg-slate-700 text-slate-200 disabled:opacity-50"
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
