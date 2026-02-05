import { useEffect } from 'react';

export interface ConfirmDialogProps {
  open: boolean;
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'default';
  onConfirm: () => void;
  onCancel: () => void;
}

const variantStyles = {
  danger: {
    border: 'border-rose-500/40',
    shadow: 'shadow-[0_20px_70px_rgba(220,38,38,0.3)]',
    button: 'border-rose-500/50 bg-rose-500/20 text-rose-200 hover:border-rose-400 hover:bg-rose-500/30',
  },
  warning: {
    border: 'border-amber-500/40',
    shadow: 'shadow-[0_20px_70px_rgba(245,158,11,0.2)]',
    button: 'border-amber-500/50 bg-amber-500/20 text-amber-200 hover:border-amber-400 hover:bg-amber-500/30',
  },
  default: {
    border: 'border-slate-800/60',
    shadow: 'shadow-[0_20px_70px_rgba(0,0,0,0.5)]',
    button: 'btn btn-primary',
  },
};

export function ConfirmDialog({
  open,
  title = 'Confirm',
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [open, onCancel]);

  if (!open) return null;

  const styles = variantStyles[variant];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl">
      <div className={`card w-full max-w-md ${styles.border} bg-slate-900/80 backdrop-blur-2xl ${styles.shadow}`}>
        <h3 className="text-xl font-semibold text-white">{title}</h3>
        <p className="mt-3 text-sm text-slate-400">{message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            {cancelLabel}
          </button>
          <button onClick={onConfirm} className={`rounded-xl border px-4 py-2 text-sm font-medium transition ${styles.button}`}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
