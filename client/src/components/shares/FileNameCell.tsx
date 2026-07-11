import { Folder, File as FileIcon } from 'lucide-react';
import { formatFileSize } from './sharesFormat';

interface FileNameCellProps {
  isDirectory: boolean;
  name: string | null;   // FileShare.file_name is nullable
  size?: number | null;
  folderLabel: string;
  variant?: 'table' | 'card';
  className?: string;
}

export function FileNameCell({ isDirectory, name, size, folderLabel, variant = 'table', className = '' }: FileNameCellProps) {
  const icon = isDirectory
    ? <Folder className="h-4 w-4 shrink-0 text-amber-400" />
    : <FileIcon className="h-4 w-4 shrink-0 text-slate-400" />;
  const sub = isDirectory ? folderLabel : formatFileSize(size ?? null);

  if (variant === 'card') {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        {icon}
        <div className="min-w-0">
          <p className="font-semibold text-white truncate">{name}</p>
          <p className="text-xs text-slate-400">{sub}</p>
        </div>
      </div>
    );
  }
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {icon}
      <div>
        <div className="font-semibold text-white">{name}</div>
        <div className="text-xs sm:text-sm text-slate-400 mt-0.5">{sub}</div>
      </div>
    </div>
  );
}
