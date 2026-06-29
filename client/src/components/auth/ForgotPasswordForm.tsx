import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { recoveryReset } from '../../api/recovery-codes';

interface Props { onDone: () => void; }

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

  const field = 'w-full rounded-lg border border-slate-800 bg-slate-950-secondary px-3 py-2 text-sm';
  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-xs text-slate-100-tertiary">{t('forgot.hint')}</p>
      {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{error}</div>}
      <label className="block space-y-1">
        <span className="text-xs text-slate-100-secondary">{t('forgot.username')}</span>
        <input className={field} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
      </label>
      <label className="block space-y-1">
        <span className="text-xs text-slate-100-secondary">{t('forgot.code')}</span>
        <input className={field} value={code} onChange={(e) => setCode(e.target.value)} required />
      </label>
      <label className="block space-y-1">
        <span className="text-xs text-slate-100-secondary">{t('forgot.newPassword')}</span>
        <input type="password" className={field} autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required />
      </label>
      <label className="block space-y-1">
        <span className="text-xs text-slate-100-secondary">{t('forgot.confirm')}</span>
        <input type="password" className={field} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
      </label>
      <div className="flex gap-2">
        <button type="submit" disabled={loading} className="flex-1 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
          {loading ? t('forgot.resetting') : t('forgot.reset')}
        </button>
        <button type="button" onClick={onDone} className="rounded-lg border border-slate-800 px-3 py-2 text-sm text-slate-100-secondary">
          {t('forgot.back')}
        </button>
      </div>
    </form>
  );
};
