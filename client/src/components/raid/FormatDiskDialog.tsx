import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { AvailableDisk } from '../../api/raid';

export interface FormatDiskDialogProps {
  disk: AvailableDisk;
  busy: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onClose: () => void;
}

export const FormatDiskDialog: React.FC<FormatDiskDialogProps> = ({
  disk,
  busy,
  onSubmit,
  onClose,
}) => {
  const { t } = useTranslation(['system', 'common']);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl" onClick={onClose}>
      <div className="card w-full max-w-[95vw] sm:max-w-md border-rose-500/40 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(220,38,38,0.3)]" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-xl font-semibold text-white">{t('system:raid.formatDialog.title')}</h3>
        <p className="mt-2 text-sm text-slate-400">
          {t('system:raid.formatDialog.formatDisk')} <span className="font-medium text-slate-200">/dev/{disk.name}</span>
        </p>
        <form onSubmit={onSubmit} className="mt-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300">{t('system:raid.formatDialog.filesystem')}</label>
            <select
              name="filesystem"
              defaultValue="ext4"
              className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              <option value="ext4">ext4</option>
              <option value="ext3">ext3</option>
              <option value="xfs">xfs</option>
              <option value="btrfs">btrfs</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300">{t('system:raid.formatDialog.label')}</label>
            <input
              name="label"
              type="text"
              placeholder={t('system:raid.formatDialog.labelPlaceholder')}
              className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
            >
              {t('system:raid.actions.cancel')}
            </button>
            <button
              type="submit"
              disabled={busy}
              className={`rounded-lg border px-4 py-2 text-sm transition ${
                busy
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-rose-500/40 bg-rose-500/15 text-rose-200 hover:border-rose-500/60'
              }`}
            >
              {t('system:raid.actions.format')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
