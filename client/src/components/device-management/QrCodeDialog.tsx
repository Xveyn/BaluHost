import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Eye, EyeOff, Copy } from 'lucide-react';
import toast from 'react-hot-toast';
import { Modal } from '../ui/Modal';
import type { MobileRegistrationToken } from '../../lib/api';

interface QrCodeDialogProps {
  data: MobileRegistrationToken | null;
  onClose: () => void;
}

export function QrCodeDialog({ data, onClose }: QrCodeDialogProps) {
  const { t } = useTranslation(['devices']);
  const [showToken, setShowToken] = useState(false);

  const handleClose = () => {
    setShowToken(false);
    onClose();
  };

  return (
    <Modal isOpen={!!data} onClose={handleClose} title={t('qrDialog.title')}>
      {data && (
        <>
          <div className="bg-white p-4 rounded-lg mb-4">
            <img
              src={`data:${data.qr_code.startsWith('iVBOR') ? 'image/png' : 'image/svg+xml'};base64,${data.qr_code}`}
              alt="QR Code"
              className="w-full h-auto"
            />
          </div>

          <button
            onClick={() => setShowToken(!showToken)}
            className="w-full text-xs text-slate-400 hover:text-sky-400 transition-colors py-1.5 flex items-center justify-center gap-1.5 mb-3"
          >
            {showToken ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            {showToken ? t('qrDialog.hideToken', 'Token verbergen') : t('qrDialog.showToken', 'Token manuell anzeigen')}
          </button>
          {showToken && (
            <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3 mb-4">
              <p className="text-xs text-slate-400 mb-1">{t('qrDialog.registrationToken', 'Registrierungs-Token')}:</p>
              <div className="flex items-center gap-2">
                <code className="text-sm text-white font-mono break-all flex-1">{data.token}</code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(data.token);
                    toast.success(t('qrDialog.tokenCopied', 'Token kopiert'));
                  }}
                  title={t('qrDialog.copy', 'Kopieren')}
                  className="text-slate-400 hover:text-sky-400 transition-colors p-1 flex-shrink-0"
                >
                  <Copy className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          <div className="space-y-2 text-sm text-slate-300 mb-4">
            <p>✓ {t('qrDialog.scanInfo')}</p>
            <p>✓ {t('qrDialog.tokenValidity')}</p>
            <p>✓ {t('qrDialog.deviceValidity', { days: data.device_token_validity_days, months: Math.round(data.device_token_validity_days / 30) })}</p>
            {data.vpn_config && (
              <p className="text-green-400">✓ {t('qrDialog.vpnIncluded')}</p>
            )}
          </div>

          <div className="bg-sky-500/10 border border-sky-500/30 rounded-lg p-3 mb-4">
            <p className="text-xs text-sky-300 font-semibold mb-1.5 flex items-center gap-1.5">
              🔔 {t('qrDialog.reminders')}
            </p>
            <p className="text-xs text-slate-300">
              {t('qrDialog.remindersDesc')}
            </p>
          </div>

          <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
            <p className="text-xs text-slate-400 mb-1">{t('qrDialog.expiresAt')}</p>
            <p className="text-sm text-white font-mono">
              {new Date(data.expires_at).toLocaleString()}
            </p>
          </div>
        </>
      )}
    </Modal>
  );
}
