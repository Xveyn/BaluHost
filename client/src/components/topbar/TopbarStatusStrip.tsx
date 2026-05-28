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
    <div className="flex items-center gap-2">
      {pills.map((pill) => (
        <PillRenderer key={pill.id} pill={pill} />
      ))}
    </div>
  );
}
