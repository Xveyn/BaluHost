import { createElement } from 'react';
import { useTranslation } from 'react-i18next';
import { Pill } from '../ui/Pill';
import { AlwaysAwakePill } from './pills/AlwaysAwakePill';
import { resolveIcon } from './iconMap';
import { resolvePluginString } from '../../lib/pluginI18n';
import type { PillState } from '../../api/statusBar';

export function PillRenderer({ pill, flat }: { pill: PillState; flat?: boolean }) {
  const { t } = useTranslation('statusBar');
  if (pill.id === 'always_awake') {
    return <AlwaysAwakePill pill={pill} flat={flat} />;
  }
  // Plugin pills carry their own translations; core pills live in the app bundle.
  const label = pill.translations
    ? resolvePluginString(pill.translations, pill.label_key, pill.label_text ?? '')
    : t(pill.label_key, { ...(pill.label_params ?? {}) });
  const value = pill.value_key
    ? t(pill.value_key, { ...(pill.value_params ?? {}), defaultValue: pill.value ?? '' })
    : (pill.value ?? undefined);

  const iconComp = resolveIcon(pill.icon);
  const icon = iconComp ? createElement(iconComp, { className: 'h-3.5 w-3.5' }) : undefined;
  return (
    <Pill tone={pill.tone} label={label} value={value} href={pill.href} icon={icon} flat={flat} />
  );
}
