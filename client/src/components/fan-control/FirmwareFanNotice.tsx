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

// Exactly the four scalars the PUT accepts (backend/app/schemas/
// gpu_fan_acoustics.py, GpuFanAcousticsValues). `read_acoustics` deliberately
// enumerates whatever the card exposes instead of hardcoding four names, so
// on kernel 6.13+ the status also carries `fan_zero_rpm_enable` and
// `fan_zero_rpm_stop_temperature` — nodes the PUT silently drops because they
// are in neither the schema nor the write allowlist. Rendering a slider for
// them would produce a control that visibly moves and changes nothing, so the
// UI only offers what it can actually set (#516).
const SETTABLE_NODES = [
  'fan_target_temperature',
  'acoustic_limit_rpm_threshold',
  'acoustic_target_rpm_threshold',
  'fan_minimum_pwm',
] as const;

// The reported nodes the UI offers, in a stable order.
function settableNodes(
  nodes: Record<string, GpuAcousticsNode>,
): [string, GpuAcousticsNode][] {
  return SETTABLE_NODES.filter((k) => nodes[k] !== undefined).map(
    (k) => [k as string, nodes[k]] as [string, GpuAcousticsNode],
  );
}

// Derive slider positions from the nodes the server reports: the observed
// desired value if BaluHost is managing it, otherwise the card's current
// value. Shared between the initial fetch and every apply/reset response so
// the sliders always reflect what the server actually holds, never a stale
// pre-request draft.
function draftFromNodes(nodes: Record<string, GpuAcousticsNode>): Record<string, number> {
  return Object.fromEntries(
    settableNodes(nodes).map(([k, n]) => [k, n.desired ?? n.current]),
  );
}

// A node counts as managed exactly when the server holds a `desired` for it.
// `null` means "hands off" (spec section 1) — and that state has to stay
// reachable through the UI, otherwise a single click on Apply would put all
// four values under BaluHost's management for every future startup.
function managedFromNodes(nodes: Record<string, GpuAcousticsNode>): Record<string, boolean> {
  return Object.fromEntries(
    settableNodes(nodes).map(([k, n]) => [k, n.desired !== null && n.desired !== undefined]),
  );
}

// A 503 from the PUT means the stored configuration is unreadable or could
// not be saved — the card is not at fault, and the message must not read as
// if it were.
function isConfigUnavailable(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 503;
}

export default function FirmwareFanNotice({ fanId }: Props) {
  const { t } = useTranslation(['system']);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<GpuAcousticsStatus | null>(null);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [managed, setManaged] = useState<Record<string, boolean>>({});
  const [applyError, setApplyError] = useState<string | null>(null);
  const [acousticsBusy, setAcousticsBusy] = useState(false);

  useEffect(() => {
    getGpuAcoustics()
      .then((s) => {
        setStatus(s);
        setDraft(draftFromNodes(s.nodes));
        setManaged(managedFromNodes(s.nodes));
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
    setApplyError(null);
    try {
      const next = await setGpuAcoustics(values);
      setStatus(next);
      setDraft(draftFromNodes(next.nodes));
      setManaged(managedFromNodes(next.nodes));

      // A 200 does not mean the card took the values. `write_acoustic` writes,
      // then reads back — because on this card an accepted write proves
      // nothing (#480) — and reports the outcome per node in `writes`. A
      // rejected value is not stored as `desired` either, so the slider and
      // its checkbox snap back to the state the server really holds.
      const rejected = Object.entries(next.writes ?? {})
        .filter(([, write]) => !write.ok)
        .map(([name]) => name);

      if (rejected.length > 0) {
        const message = t('system:fanControl.gpu.acoustics.writeFailed', {
          nodes: rejected
            .map((name) => t(`system:fanControl.gpu.acoustics.${name}`))
            .join(', '),
        });
        setApplyError(message);
        toast.error(message);
      } else {
        toast.success(successMessage);
      }
    } catch (err) {
      if (isConfigUnavailable(err)) {
        const message = t('system:fanControl.gpu.acoustics.configUnavailable');
        setApplyError(message);
        toast.error(message);
      } else {
        handleApiError(err, t('system:fanControl.gpu.acoustics.title'));
      }
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

              {settableNodes(status.nodes).map(([name, node]) => (
                <div key={name} className="space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <label className="flex items-center gap-2 text-xs text-slate-300">
                      <input
                        type="checkbox"
                        aria-label={`${t('system:fanControl.gpu.acoustics.managed')}: ${
                          t(`system:fanControl.gpu.acoustics.${name}`)}`}
                        checked={managed[name] ?? false}
                        onChange={(e) =>
                          setManaged({ ...managed, [name]: e.target.checked })}
                        className="accent-sky-500"
                      />
                      <span>
                        {t(`system:fanControl.gpu.acoustics.${name}`)}: {draft[name]}
                      </span>
                    </label>
                    <span
                      data-testid={`gpu-acoustics-current-${name}`}
                      className="text-xs text-slate-500 whitespace-nowrap"
                    >
                      {t('system:fanControl.gpu.acoustics.currentLabel')}: {node.current}
                    </span>
                  </div>
                  <input
                    type="range"
                    aria-label={t(`system:fanControl.gpu.acoustics.${name}`)}
                    min={node.minimum}
                    max={node.maximum}
                    value={draft[name]}
                    disabled={!managed[name] || acousticsBusy}
                    onChange={(e) =>
                      setDraft({ ...draft, [name]: parseInt(e.target.value, 10) })}
                    className="w-full disabled:opacity-40"
                  />
                </div>
              ))}

              <p className="text-xs text-slate-400">
                {t('system:fanControl.gpu.acoustics.managedHint')}
              </p>
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
              {applyError && (
                <p data-testid="gpu-acoustics-error" className="text-xs text-red-400">
                  {applyError}
                </p>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => applyAcoustics(
                    // Only checked values are sent as a wish; every other node
                    // goes out as `null` — "stop managing it". Sending the
                    // whole draft would make one click on Apply adopt all four
                    // values, and there would be no way back to "BaluHost only
                    // manages the target temperature".
                    Object.fromEntries(settableNodes(status.nodes).map(
                      ([name]) => [name, managed[name] ? draft[name] : null],
                    )),
                    t('system:fanControl.gpu.acoustics.saveSuccess'),
                  )}
                  disabled={acousticsBusy}
                  className="px-3 py-1 text-sm rounded bg-sky-500 text-white disabled:opacity-50"
                >
                  {t('system:fanControl.gpu.acoustics.save')}
                </button>
                <button
                  onClick={() => applyAcoustics(
                    Object.fromEntries(settableNodes(status.nodes).map(([k]) => [k, null])),
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
