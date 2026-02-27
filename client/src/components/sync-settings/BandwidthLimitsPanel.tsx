import { useState, useEffect } from 'react';
import { HardDrive } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface BandwidthLimitsPanelProps {
  initialUpload: number | null;
  initialDownload: number | null;
  onSave: (upload: number | null, download: number | null) => Promise<boolean>;
}

export function BandwidthLimitsPanel({ initialUpload, initialDownload, onSave }: BandwidthLimitsPanelProps) {
  const { t } = useTranslation('settings');
  const [uploadLimit, setUploadLimit] = useState<number | null>(initialUpload);
  const [downloadLimit, setDownloadLimit] = useState<number | null>(initialDownload);

  useEffect(() => {
    setUploadLimit(initialUpload);
    setDownloadLimit(initialDownload);
  }, [initialUpload, initialDownload]);

  return (
    <div className="mb-6">
      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <HardDrive className="w-5 h-5" />
        {t('sync.bandwidthLimits')}
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input
          type="number"
          placeholder={t('sync.uploadLimit')}
          value={uploadLimit || ''}
          onChange={(e) => setUploadLimit(e.target.value ? parseInt(e.target.value) : null)}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
        />
        <input
          type="number"
          placeholder={t('sync.downloadLimit')}
          value={downloadLimit || ''}
          onChange={(e) => setDownloadLimit(e.target.value ? parseInt(e.target.value) : null)}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
        />
        <button
          onClick={() => onSave(uploadLimit, downloadLimit)}
          className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors"
        >
          {t('sync.saveLimits')}
        </button>
      </div>
    </div>
  );
}
