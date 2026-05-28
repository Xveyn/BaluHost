import { createElement } from 'react';
import { Pill } from '../ui/Pill';
import { AlwaysAwakePill } from './pills/AlwaysAwakePill';
import { resolveIcon } from './iconMap';
import type { PillState } from '../../api/statusBar';

export function PillRenderer({ pill, flat }: { pill: PillState; flat?: boolean }) {
  if (pill.id === 'always_awake') {
    return <AlwaysAwakePill pill={pill} flat={flat} />;
  }
  const iconComp = resolveIcon(pill.icon);
  const icon = iconComp ? createElement(iconComp, { className: 'h-3.5 w-3.5' }) : undefined;
  return (
    <Pill
      tone={pill.tone}
      label={pill.label}
      value={pill.value ?? undefined}
      href={pill.href}
      icon={icon}
      flat={flat}
    />
  );
}
