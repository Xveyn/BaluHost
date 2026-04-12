import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

export default function ImpersonationBanner() {
  const { t } = useTranslation('common');
  const { isImpersonating, impersonationOrigin, user, endImpersonation } = useAuth();

  if (!isImpersonating || !user || !impersonationOrigin) return null;

  const roleLabel = user.role === 'admin' ? t('impersonation.role.admin') : t('impersonation.role.user');

  return (
    <div
      role="alert"
      className="fixed top-0 right-0 left-0 lg:left-72 z-40 flex items-center justify-between gap-3 bg-amber-500 px-4 py-2 text-sm font-medium text-amber-950 shadow-md"
    >
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4" />
        <span>
          {t('impersonation.banner.viewingAs', { username: user.username, role: roleLabel })}
        </span>
      </div>
      <button
        type="button"
        onClick={endImpersonation}
        className="rounded-md border border-amber-900/40 bg-amber-100/60 px-3 py-1 text-xs font-semibold text-amber-950 transition hover:bg-amber-100"
      >
        {t('impersonation.banner.backToAdmin', { admin: impersonationOrigin })}
      </button>
    </div>
  );
}
