import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { formatBytes } from '../../lib/formatters';
import type { DuplicateFileEntry, DuplicateResolution, DuplicateDecision } from '../../contexts/UploadContext';

interface DuplicateDialogProps {
  duplicates: DuplicateFileEntry[];
  /** The full file list being uploaded — used to detect size match for "likely identical" */
  uploadFiles: FileList;
  onConfirm: (decisions: DuplicateDecision[]) => void;
  onCancel: () => void;
}

export function DuplicateDialog({ duplicates, uploadFiles, onConfirm, onCancel }: DuplicateDialogProps) {
  const { t } = useTranslation(['fileManager']);

  // Build a size lookup from the files being uploaded
  const uploadSizeMap = new Map<string, number>();
  for (let i = 0; i < uploadFiles.length; i++) {
    uploadSizeMap.set(uploadFiles[i].name, uploadFiles[i].size);
  }

  const [decisions, setDecisions] = useState<Map<string, DuplicateResolution>>(() => {
    const map = new Map<string, DuplicateResolution>();
    for (const d of duplicates) {
      map.set(d.filename, 'overwrite');
    }
    return map;
  });

  const setResolution = (filename: string, resolution: DuplicateResolution) => {
    setDecisions(prev => {
      const next = new Map(prev);
      next.set(filename, resolution);
      return next;
    });
  };

  const applyToAll = (resolution: DuplicateResolution) => {
    setDecisions(prev => {
      const next = new Map(prev);
      for (const key of next.keys()) {
        next.set(key, resolution);
      }
      return next;
    });
  };

  const handleConfirm = () => {
    const result: DuplicateDecision[] = [];
    for (const [filename, resolution] of decisions) {
      result.push({ filename, resolution });
    }
    onConfirm(result);
  };

  const resolutionOptions: { value: DuplicateResolution; label: string }[] = [
    { value: 'overwrite', label: t('fileManager:duplicates.overwrite') },
    { value: 'skip', label: t('fileManager:duplicates.skip') },
    { value: 'keep-both', label: t('fileManager:duplicates.keepBoth') },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg mx-4 rounded-2xl border border-slate-800/60 bg-slate-900/95 shadow-[0_20px_70px_rgba(0,0,0,0.5)]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800/40 px-5 py-4">
          <h2 className="text-base font-semibold text-white">
            {t('fileManager:duplicates.title')}
          </h2>
          <button
            onClick={onCancel}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Description */}
        <div className="px-5 pt-3 pb-1">
          <p className="text-sm text-slate-400">
            {t('fileManager:duplicates.description')}
          </p>
        </div>

        {/* Apply to all */}
        {duplicates.length > 1 && (
          <div className="px-5 py-2 flex items-center gap-2">
            <span className="text-xs text-slate-500">{t('fileManager:duplicates.applyToAll')}:</span>
            {resolutionOptions.map(opt => (
              <button
                key={opt.value}
                onClick={() => applyToAll(opt.value)}
                className="rounded-lg border border-slate-700/70 bg-slate-800/60 px-2.5 py-1 text-xs text-slate-300 hover:border-sky-500/40 hover:text-white transition-colors"
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}

        {/* File list */}
        <div className="max-h-72 overflow-y-auto px-5 py-2 space-y-2">
          {duplicates.map(dup => {
            const uploadSize = uploadSizeMap.get(dup.filename);
            const sameSize = uploadSize != null && uploadSize === dup.size_bytes;
            const likelyIdentical = sameSize && dup.checksum != null;
            const current = decisions.get(dup.filename) ?? 'overwrite';

            return (
              <div
                key={dup.filename}
                className="border border-slate-800/60 bg-slate-950/40 rounded-xl p-3"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-200 truncate">{dup.filename}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-[11px] text-slate-500">
                        {t('fileManager:duplicates.existingSize', { size: formatBytes(dup.size_bytes) })}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {t('fileManager:duplicates.existingModified', {
                          date: new Date(dup.modified_at).toLocaleDateString(),
                        })}
                      </span>
                    </div>
                  </div>
                  {likelyIdentical && (
                    <span className="shrink-0 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                      {t('fileManager:duplicates.likelyIdentical')}
                    </span>
                  )}
                </div>

                {/* Resolution buttons */}
                <div className="flex flex-wrap gap-1.5">
                  {resolutionOptions.map(opt => (
                    <button
                      key={opt.value}
                      onClick={() => setResolution(dup.filename, opt.value)}
                      className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                        current === opt.value
                          ? 'border-sky-500/60 bg-sky-500/20 text-sky-300'
                          : 'border-slate-700/70 bg-slate-800/40 text-slate-400 hover:text-slate-200 hover:border-slate-600'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-slate-800/40 px-5 py-4">
          <button
            onClick={onCancel}
            className="rounded-xl border border-slate-700/70 bg-slate-800/60 px-4 py-2 text-sm font-medium text-slate-300 hover:text-white transition-colors"
          >
            {t('fileManager:duplicates.cancel')}
          </button>
          <button
            onClick={handleConfirm}
            className="rounded-xl border border-sky-500/40 bg-sky-500/20 px-4 py-2 text-sm font-medium text-sky-300 hover:bg-sky-500/30 transition-colors"
          >
            {t('fileManager:duplicates.proceed')}
          </button>
        </div>
      </div>
    </div>
  );
}
