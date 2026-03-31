import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Copy, Download, Eye, EyeOff } from 'lucide-react';
import type { VPNProfileExport } from '../../api/remote-servers';
import { Modal } from '../ui/Modal';
import { formatBytes } from '../../lib/formatters';

interface VPNProfileExportDialogProps {
  open: boolean;
  data: VPNProfileExport | null;
  onClose: () => void;
}

export function VPNProfileExportDialog({ open, data, onClose }: VPNProfileExportDialogProps) {
  const { t } = useTranslation('remoteServers');
  const [showConfig, setShowConfig] = useState(false);

  useEffect(() => {
    if (!open) setShowConfig(false);
  }, [open]);

  if (!open || !data) {
    return null;
  }

  const mime = data.qr_code && data.qr_code.startsWith('iVBOR') ? 'image/png' : 'image/svg+xml';

  const decodeConfig = (): string => {
    try {
      return atob(data.config_base64);
    } catch {
      return '';
    }
  };

  const handleCopy = async () => {
    const content = decodeConfig();
    if (!content) {
      toast.error(t('vpn.export.copyFailed'));
      return;
    }
    try {
      await navigator.clipboard.writeText(content);
      toast.success(t('vpn.export.copySuccess'));
    } catch {
      toast.error(t('vpn.export.copyFailed'));
    }
  };

  const handleDownload = () => {
    const content = decodeConfig();
    if (!content) {
      toast.error(t('vpn.export.downloadFailed'));
      return;
    }

    try {
      const blob = new Blob([content], { type: data.mime_type || 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = data.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch {
      toast.error(t('vpn.export.downloadFailed'));
    }
  };

  return (
    <Modal isOpen={open} onClose={onClose} title={t('vpn.export.title')} size="lg">
      <div className="space-y-4">
        <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-3 text-sm text-slate-300">
          <p>
            <span className="text-slate-400">{t('vpn.export.profile')}:</span> {data.profile_name}
          </p>
          <p>
            <span className="text-slate-400">{t('vpn.export.type')}:</span> {data.vpn_type.toUpperCase()}
          </p>
          <p>
            <span className="text-slate-400">{t('vpn.export.size')}:</span> {formatBytes(data.size_bytes)}
          </p>
        </div>

        {data.mode === 'qr' && data.qr_code ? (
          <>
            <div className="mx-auto w-full max-w-md rounded-lg bg-white p-4">
              <img
                src={`data:${mime};base64,${data.qr_code}`}
                alt={t('vpn.export.qrAlt')}
                className="h-auto w-full"
              />
            </div>
            <p className="text-xs text-slate-400">{t('vpn.export.qrHint')}</p>
          </>
        ) : (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
            {t('vpn.export.downloadHint')}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setShowConfig((prev) => !prev)}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:border-slate-600"
          >
            {showConfig ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            {showConfig ? t('vpn.export.hideConfig') : t('vpn.export.showConfig')}
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:border-slate-600"
          >
            <Copy className="h-4 w-4" />
            {t('vpn.export.copyConfig')}
          </button>
          <button
            type="button"
            onClick={handleDownload}
            className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500"
          >
            <Download className="h-4 w-4" />
            {t('vpn.export.downloadConfig')}
          </button>
        </div>

        {showConfig && (
          <pre className="max-h-64 overflow-auto rounded-lg border border-slate-700 bg-slate-900 p-3 text-xs text-slate-300">
            {decodeConfig()}
          </pre>
        )}
      </div>
    </Modal>
  );
}
