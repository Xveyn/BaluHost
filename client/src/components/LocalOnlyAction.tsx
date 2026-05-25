import React from 'react';
import { Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChannelStatus } from '../hooks/useChannelStatus';

interface LocalOnlyActionProps {
  children: React.ReactElement<{ disabled?: boolean }>;
  hint?: string;
}

/**
 * Wraps an interactive element (typically a button). When the current channel
 * is remote, the child is rendered with disabled=true and shown alongside a
 * Lock icon plus a native browser tooltip explaining why.
 *
 * While the channel status is still loading, the child renders unchanged to
 * avoid a layout flicker. The backend remains the authoritative gate (403).
 */
export function LocalOnlyAction({ children, hint }: LocalOnlyActionProps) {
  const { t } = useTranslation('common');
  const { isLocal, isLoading } = useChannelStatus();

  if (isLocal || isLoading) return children;

  const disabledChild = React.cloneElement(children, { disabled: true });
  const tooltip = hint ?? t('local_only_action_hint');

  return (
    <span className="inline-flex items-center gap-1" title={tooltip}>
      {disabledChild}
      <Lock className="h-3 w-3 text-slate-400" aria-hidden="true" />
    </span>
  );
}
