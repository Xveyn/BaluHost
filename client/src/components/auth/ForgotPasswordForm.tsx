import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { recoveryReset } from '../../api/recovery-codes';

interface Props { onDone: () => void; }

const labelClass = 'text-xs font-medium uppercase tracking-[0.2em] text-slate-100-tertiary';

export const ForgotPasswordForm = ({ onDone }: Props) => {
  const { t } = useTranslation('login');
  const [username, setUsername] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (newPassword !== confirm) { setError(t('forgot.mismatch')); return; }
    setLoading(true);
    try {
      await recoveryReset(username.trim(), code.trim(), newPassword);
      toast.success(t('forgot.success'));
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('forgot.failed'));
    } finally { setLoading(false); }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
      <p className="text-sm text-slate-100-tertiary">{t('forgot.hint')}</p>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 sm:px-4 py-2.5 sm:py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      <div className="space-y-2">
        <label htmlFor="forgot-username" className={labelClass}>{t('forgot.username')}</label>
        <input
          type="text"
          id="forgot-username"
          className="input"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="forgot-code" className={labelClass}>{t('forgot.code')}</label>
        <input
          type="text"
          id="forgot-code"
          className="input font-mono tracking-wider"
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          required
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="forgot-new-password" className={labelClass}>{t('forgot.newPassword')}</label>
        <input
          type="password"
          id="forgot-new-password"
          className="input"
          autoComplete="new-password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="forgot-confirm" className={labelClass}>{t('forgot.confirm')}</label>
        <input
          type="password"
          id="forgot-confirm"
          className="input"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />
      </div>

      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={loading}
          className="btn btn-primary flex-1 touch-manipulation active:scale-[0.98] disabled:opacity-50"
        >
          {loading ? t('forgot.resetting') : t('forgot.reset')}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="btn btn-secondary"
        >
          {t('forgot.back')}
        </button>
      </div>
    </form>
  );
};
