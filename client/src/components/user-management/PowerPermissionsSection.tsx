import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Moon, Sun, Power, Wifi, MonitorOff, LockOpen, Loader2 } from 'lucide-react';
import {
  getUserPowerPermissions,
  updateUserPowerPermissions,
  type UserPowerPermissions,
  type UserPowerPermissionsUpdate,
} from '../../api/powerPermissions';
import { handleApiError } from '../../lib/errorHandling';
import toast from 'react-hot-toast';

interface PowerPermissionsSectionProps {
  userId: number;
  userRole: string;
}

interface PermissionToggle {
  key: keyof UserPowerPermissionsUpdate;
  icon: React.ReactNode;
  impliedBy?: keyof UserPowerPermissionsUpdate;
  implies?: keyof UserPowerPermissionsUpdate;
}

// Maps an API field name to its i18n item key under
// admin:users.systemPermissions.items.*
const FIELD_TO_I18N: Record<keyof UserPowerPermissionsUpdate, string> = {
  can_soft_sleep: 'softSleep',
  can_wake: 'wake',
  can_suspend: 'suspend',
  can_wol: 'wol',
  can_toggle_desktop: 'toggleDesktop',
  can_unlock_session: 'unlockSession',
};

const PERMISSION_TOGGLES: PermissionToggle[] = [
  { key: 'can_soft_sleep', icon: <Moon className="h-4 w-4" />, implies: 'can_wake' },
  { key: 'can_wake', icon: <Sun className="h-4 w-4" />, impliedBy: 'can_soft_sleep' },
  { key: 'can_suspend', icon: <Power className="h-4 w-4" />, implies: 'can_wol' },
  { key: 'can_wol', icon: <Wifi className="h-4 w-4" />, impliedBy: 'can_suspend' },
  { key: 'can_toggle_desktop', icon: <MonitorOff className="h-4 w-4" /> },
  { key: 'can_unlock_session', icon: <LockOpen className="h-4 w-4" /> },
];

export function PowerPermissionsSection({ userId, userRole }: PowerPermissionsSectionProps) {
  const { t, i18n } = useTranslation('admin');
  const [permissions, setPermissions] = useState<UserPowerPermissions | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (userRole === 'admin') return;
    setLoading(true);
    getUserPowerPermissions(userId)
      .then(setPermissions)
      .catch(() => setPermissions(null))
      .finally(() => setLoading(false));
  }, [userId, userRole]);

  if (userRole === 'admin') return null;

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('users.systemPermissions.loading')}
      </div>
    );
  }

  const handleToggle = async (key: keyof UserPowerPermissionsUpdate, newValue: boolean) => {
    setSaving(true);
    try {
      const update: UserPowerPermissionsUpdate = { [key]: newValue };
      const result = await updateUserPowerPermissions(userId, update);
      setPermissions(result);
      toast.success(t('users.systemPermissions.saved'));
    } catch (error) {
      handleApiError(error, t('users.systemPermissions.saveError'));
    } finally {
      setSaving(false);
    }
  };

  const isImplied = (toggle: PermissionToggle): boolean => {
    if (!toggle.impliedBy || !permissions) return false;
    return permissions[toggle.impliedBy] === true;
  };

  return (
    <div className="border-t border-slate-800 pt-3 mt-3">
      <h3 className="text-sm font-medium text-slate-300 mb-1">
        {t('users.systemPermissions.title')}
      </h3>
      <p className="text-xs text-slate-500 mb-3">
        {t('users.systemPermissions.description')}
      </p>

      <div className="space-y-2">
        {PERMISSION_TOGGLES.map((toggle) => {
          const value = permissions?.[toggle.key] ?? false;
          const implied = isImplied(toggle);
          const i18nKey = FIELD_TO_I18N[toggle.key];

          return (
            <div key={toggle.key} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-slate-400">{toggle.icon}</span>
                <div>
                  <span className="text-sm text-slate-200">
                    {t(`users.systemPermissions.items.${i18nKey}.label`)}
                  </span>
                  <span className="text-xs text-slate-500 ml-2">
                    {t(`users.systemPermissions.items.${i18nKey}.desc`)}
                  </span>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={value}
                disabled={saving || implied}
                onClick={() => handleToggle(toggle.key, !value)}
                title={
                  implied && toggle.impliedBy
                    ? t('users.systemPermissions.impliedBy', {
                        name: t(`users.systemPermissions.items.${FIELD_TO_I18N[toggle.impliedBy]}.label`),
                      })
                    : undefined
                }
                className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors
                  ${value ? 'bg-sky-500' : 'bg-slate-700'}
                  ${implied ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}
                  ${saving ? 'opacity-50' : ''}
                `}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform
                    ${value ? 'translate-x-4' : 'translate-x-0.5'}
                  `}
                />
              </button>
            </div>
          );
        })}
      </div>

      {permissions?.granted_by_username && (
        <p className="text-xs text-slate-500 mt-2">
          {t('users.systemPermissions.lastChangedBy', {
            name: permissions.granted_by_username,
            date: permissions.granted_at
              ? new Date(permissions.granted_at).toLocaleDateString(i18n.language)
              : '',
          })}
        </p>
      )}
    </div>
  );
}
