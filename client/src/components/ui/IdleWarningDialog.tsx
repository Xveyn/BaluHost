import { useEffect } from 'react';
import { Clock } from 'lucide-react';

interface IdleWarningDialogProps {
  open: boolean;
  secondsRemaining: number;
  onStayLoggedIn: () => void;
  onLogoutNow: () => void;
}

export function IdleWarningDialog({ open, secondsRemaining, onStayLoggedIn, onLogoutNow }: IdleWarningDialogProps) {
  useEffect(() => {
    if (!open) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onStayLoggedIn();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [open, onStayLoggedIn]);

  if (!open) return null;

  const minutes = Math.floor(secondsRemaining / 60);
  const seconds = secondsRemaining % 60;
  const timeDisplay = `${minutes}:${seconds.toString().padStart(2, '0')}`;
  const isUrgent = secondsRemaining <= 10;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl">
      <div className="card w-full max-w-md border-amber-500/40 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(245,158,11,0.2)]">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/15">
            <Clock className="h-5 w-5 text-amber-400" />
          </div>
          <h3 className="text-xl font-semibold text-white">Session Timeout</h3>
        </div>

        <p className="mt-3 text-sm text-slate-400">
          You've been inactive for a while. For security, you'll be logged out automatically.
        </p>

        <div className="mt-4 flex justify-center">
          <span
            className={`text-5xl font-semibold tabular-nums transition-colors ${
              isUrgent ? 'text-rose-400' : 'text-amber-300'
            }`}
          >
            {timeDisplay}
          </span>
        </div>

        <div className="mt-6 flex justify-between gap-3">
          <button
            onClick={onLogoutNow}
            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            Log out now
          </button>
          <button
            onClick={onStayLoggedIn}
            className="rounded-xl border border-amber-500/50 bg-amber-500/20 px-4 py-2 text-sm font-medium text-amber-200 transition hover:border-amber-400 hover:bg-amber-500/30"
          >
            Stay logged in
          </button>
        </div>
      </div>
    </div>
  );
}
