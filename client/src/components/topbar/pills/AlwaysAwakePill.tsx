import { createElement } from 'react';
import { useTranslation } from 'react-i18next';
import { Pill } from '../../ui/Pill';
import { useCountdown } from '../../../hooks/useCountdown';
import { resolveIcon } from '../iconMap';
import type { PillState } from '../../../api/statusBar';

export function AlwaysAwakePill({ pill, flat }: { pill: PillState; flat?: boolean }) {
  const { t } = useTranslation('statusBar');
  const variant = pill.extra?.variant;
  const expires = typeof pill.extra?.expires_in_seconds === 'number'
    ? (pill.extra!.expires_in_seconds as number)
    : null;
  const countdown = useCountdown(expires);

  let label: string;
  let value: string | undefined;
  if (variant === 'core_uptime') {
    label = t('pills.alwaysAwake.coreUptimeLive');
    const until = typeof pill.extra?.until === 'string' ? (pill.extra!.until as string) : undefined;
    value = until ? t('pills.alwaysAwake.coreUptimeUntil', { time: until }) : undefined;
  } else {
    label = t('pills.alwaysAwake.live');
    value = countdown ?? (expires === null ? t('pills.alwaysAwake.permanent') : pill.value ?? undefined);
  }

  const iconComp = resolveIcon(pill.icon);
  const icon = iconComp ? createElement(iconComp, { className: 'h-3.5 w-3.5' }) : undefined;
  return (
    <Pill
      tone={pill.tone}
      label={label}
      value={value}
      href={pill.href}
      icon={icon}
      flat={flat}
    />
  );
}
