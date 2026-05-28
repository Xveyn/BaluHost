import { Pill } from '../ui/Pill';
import { AlwaysAwakePill } from './pills/AlwaysAwakePill';
import { resolveIcon } from './iconMap';
import type { PillState } from '../../api/statusBar';

export function PillRenderer({ pill }: { pill: PillState }) {
  if (pill.id === 'always_awake') {
    return <AlwaysAwakePill pill={pill} />;
  }
  const Icon = resolveIcon(pill.icon);
  return (
    <Pill
      tone={pill.tone}
      label={pill.label}
      value={pill.value ?? undefined}
      href={pill.href}
      icon={Icon ? <Icon className="h-3.5 w-3.5" /> : undefined}
    />
  );
}
