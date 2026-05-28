import { Fragment } from 'react';
import { useStatusBarState } from '../../hooks/useStatusBarState';
import { PillRenderer } from './pillRenderers';
import type { StatusBarStateResponse } from '../../api/statusBar';

interface Props {
  /** When provided, renders this state and skips polling (used by the config Live Preview). */
  previewState?: StatusBarStateResponse;
}

export function TopbarStatusStrip({ previewState }: Props) {
  const { state: polled } = useStatusBarState();
  const state = previewState ?? polled;
  const pills = state?.pills ?? [];

  if (pills.length === 0) return null;

  return (
    <div className="flex items-center gap-1 rounded-full border border-slate-700/50 bg-slate-800/40 px-2 py-1 shadow-[0_4px_16px_rgba(2,6,23,0.35)] backdrop-blur-xl">
      {pills.map((pill, i) => (
        <Fragment key={pill.id}>
          {i > 0 && <span aria-hidden="true" className="mx-0.5 h-3.5 w-px bg-slate-600/60" />}
          <PillRenderer pill={pill} flat />
        </Fragment>
      ))}
    </div>
  );
}
