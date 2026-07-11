import { useTranslation } from 'react-i18next';

interface PermissionBadgesProps {
  canRead?: boolean;
  canWrite?: boolean;
  canDelete?: boolean;
  size?: 'sm' | 'md';
}

export function PermissionBadges({ canRead, canWrite, canDelete, size = 'md' }: PermissionBadgesProps) {
  const { t } = useTranslation('shares');
  const pad = size === 'sm' ? 'px-2 py-0.5' : 'px-2.5 py-1';
  return (
    <>
      {canRead && (
        <span className={`${pad} border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold`}>
          {t('permissions.read')}
        </span>
      )}
      {canWrite && (
        <span className={`${pad} border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold`}>
          {t('permissions.write')}
        </span>
      )}
      {canDelete && (
        <span className={`${pad} border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold`}>
          {t('permissions.delete')}
        </span>
      )}
    </>
  );
}
