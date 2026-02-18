import { X } from 'lucide-react';
import type { FileItem } from './types';

export interface RenameDialogProps {
  file: FileItem;
  newName: string;
  onNameChange: (name: string) => void;
  onRename: () => void;
  onClose: () => void;
}

export function RenameDialog({
  file,
  newName,
  onNameChange,
  onRename,
  onClose,
}: RenameDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl p-4">
      <div className="card w-full max-w-md border-slate-800/60 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(0,0,0,0.5)]">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800/60 -mx-4 sm:-mx-6 px-4 sm:px-6">
          <div>
            <h3 className="text-lg font-semibold text-white">Rename {file.type === 'directory' ? 'Folder' : 'File'}</h3>
            <p className="mt-0.5 text-xs text-slate-400">Update the display name without affecting the contents.</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="pt-5">
          <input
            type="text"
            value={newName}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="Enter new name"
            className="input"
            autoFocus
            onKeyDown={(e) => e.key === 'Enter' && onRename()}
          />
        </div>
        <div className="flex justify-end gap-3 pt-5 mt-5 border-t border-slate-800/40 -mx-4 sm:-mx-6 px-4 sm:px-6">
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            Cancel
          </button>
          <button
            onClick={onRename}
            className="btn btn-primary"
          >
            Rename
          </button>
        </div>
      </div>
    </div>
  );
}
