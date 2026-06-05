import { useState, useEffect } from 'react';
import { HardDrive } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface BandwidthLimitsPanelProps {
  initialUpload: number | null;
  initialDownload: number | null;
  onSave: (upload: number | null, download: number | null) => Promise<boolean>;
}

const inputClass =
  'w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500';

export function BandwidthLimitsPanel({ initialUpload, initialDownload, onSave }: BandwidthLimitsPanelProps) {
  const { t } = useTranslation('devices');
  const [uploadLimit, setUploadLimit] = useState<number | null>(initialUpload);
  const [downloadLimit, setDownloadLimit] = useState<number | null>(initialDownload);

  useEffect(() => {
    setUploadLimit(initialUpload);
    setDownloadLimit(initialDownload);
  }, [initialUpload, initialDownload]);

  return (
    <div className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
      <h3 className="mb-3 text-sm font-medium text-slate-300 flex items-center gap-2">
        <HardDrive className="h-4 w-4" />
        {t('schedules.bandwidthLimits')}
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input
          type="number"
          placeholder={t('schedules.uploadLimit')}
          value={uploadLimit ?? ''}
          onChange={(e) => setUploadLimit(e.target.value ? parseInt(e.target.value) : null)}
          className={inputClass}
        />
        <input
          type="number"
          placeholder={t('schedules.downloadLimit')}
          value={downloadLimit ?? ''}
          onChange={(e) => setDownloadLimit(e.target.value ? parseInt(e.target.value) : null)}
          className={inputClass}
        />
        <button
          onClick={() => onSave(uploadLimit, downloadLimit)}
          className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/20 transition"
        >
          {t('schedules.saveLimits')}
        </button>
      </div>
    </div>
  );
}
