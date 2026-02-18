import { X, AlertTriangle } from 'lucide-react';
import type { FileItem } from './types';

export interface DeleteDialogProps {
  file: FileItem;
  onConfirm: () => void;
  onClose: () => void;
}

export function DeleteDialog({ file, onConfirm, onClose }: DeleteDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl p-4">
      <div className="card w-full max-w-md border-rose-500/40 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(220,38,38,0.3)]">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800/60 -mx-4 sm:-mx-6 px-4 sm:px-6">
          <h3 className="text-lg font-semibold text-white">Confirm Delete</h3>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="pt-5">
          <div className="flex items-start gap-3 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20">
            <AlertTriangle className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
            <p className="text-sm text-slate-300">
              Are you sure you want to remove <span className="font-semibold text-white">{file.name}</span>?
              {file.type === 'directory' && (
                <span className="block mt-1 text-amber-300">All nested items will also be deleted.</span>
              )}
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-3 pt-5 mt-5 border-t border-slate-800/40 -mx-4 sm:-mx-6 px-4 sm:px-6">
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="rounded-xl border border-rose-500/50 bg-rose-500/20 px-4 py-2 text-sm font-medium text-rose-200 transition hover:border-rose-400 hover:bg-rose-500/30"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
