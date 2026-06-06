/** Desktop-app PIN management — visible only when 2FA is enabled. */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { getPinStatus, setPin as apiSetPin, removePin } from '../../api/pin';
import { handleApiError } from '../../lib/errorHandling';

interface Props {
  twoFactorEnabled: boolean;
}

export function DesktopPinSettings({ twoFactorEnabled }: Props) {
  const { t } = useTranslation('settings');
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pin, setPinValue] = useState('');
  const [confirm, setConfirm] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!twoFactorEnabled) { setLoading(false); return; }
    getPinStatus()
      .then((s) => setEnabled(s.pin_enabled))
      .catch(() => setEnabled(false))
      .finally(() => setLoading(false));
  }, [twoFactorEnabled]);

  const onSave = async () => {
    if (pin !== confirm) { toast.error(t('pin.mismatch')); return; }
    setBusy(true);
    try {
      await apiSetPin(pin, code);
      setEnabled(true);
      setPinValue(''); setConfirm(''); setCode('');
      toast.success(t('pin.saved'));
    } catch (err) {
      handleApiError(err, t('pin.saveError'));
    } finally {
      setBusy(false);
    }
  };

  const onRemove = async () => {
    setBusy(true);
    try {
      await removePin(code);
      setEnabled(false);
      setCode('');
      toast.success(t('pin.removed'));
    } catch (err) {
      handleApiError(err, t('pin.removeError'));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h3 className="text-lg font-semibold text-slate-100">{t('pin.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">{t('pin.description')}</p>

      {!twoFactorEnabled ? (
        <p className="mt-4 text-sm text-amber-300">{t('pin.needs2fa')}</p>
      ) : (
        <div className="mt-4 space-y-3">
          <p className="text-sm">
            <span className={enabled ? 'text-emerald-400' : 'text-slate-400'}>
              {enabled ? t('pin.enabled') : t('pin.disabled')}
            </span>
          </p>

          {!enabled && (
            <>
              <input type="password" inputMode="numeric" placeholder={t('pin.pinLabel')}
                className="input" value={pin}
                onChange={(e) => setPinValue(e.target.value.replace(/\D/g, '').slice(0, 8))} />
              <input type="password" inputMode="numeric" placeholder={t('pin.confirmLabel')}
                className="input" value={confirm}
                onChange={(e) => setConfirm(e.target.value.replace(/\D/g, '').slice(0, 8))} />
            </>
          )}

          <input type="text" inputMode="numeric" placeholder={t('pin.codeLabel')}
            className="input" value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
            autoComplete="one-time-code" />

          <div className="flex gap-2">
            {!enabled ? (
              <button className="btn btn-primary" disabled={busy || pin.length < 4 || code.length < 6} onClick={onSave}>
                {t('pin.save')}
              </button>
            ) : (
              <button className="btn btn-danger" disabled={busy || code.length < 6} onClick={onRemove}>
                {t('pin.remove')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
