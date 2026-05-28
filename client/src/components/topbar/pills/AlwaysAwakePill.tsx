import React from 'react';
import { Pill } from '../../ui/Pill';
import { useCountdown } from '../../../hooks/useCountdown';
import { resolveIcon } from '../iconMap';
import type { PillState } from '../../../api/statusBar';

export function AlwaysAwakePill({ pill }: { pill: PillState }) {
  const expires = typeof pill.extra?.expires_in_seconds === 'number'
    ? (pill.extra!.expires_in_seconds as number)
    : null;
  const countdown = useCountdown(expires);
  const value = countdown ?? pill.value ?? undefined;

  const Icon = resolveIcon(pill.icon);
  return (
    <Pill
      tone={pill.tone}
      label={pill.label}
      value={value}
      href={pill.href}
      icon={Icon ? <Icon className="h-3.5 w-3.5" /> : undefined}
    />
  );
}
