import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { X, Monitor, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import {
  verifyDesktopPairingCode,
  approveDesktopPairingCode,
  denyDesktopPairingCode,
  type DesktopPairingApprovalInfo,
} from '../api/devices';

interface DesktopPairingDialogProps {
  open: boolean;
  onClose: () => void;
  onPaired: () => void;
}

type DialogState = 'input' | 'confirm' | 'success' | 'error';

const platformLabels: Record<string, string> = {
  windows: 'Windows',
  mac: 'macOS',
  linux: 'Linux',
};

export default function DesktopPairingDialog({
  open,
  onClose,
  onPaired,
}: DesktopPairingDialogProps) {
  const { t } = useTranslation(['devices', 'common']);
  const [state, setState] = useState<DialogState>('input');
  const [code, setCode] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [deviceInfo, setDeviceInfo] = useState<DesktopPairingApprovalInfo | null>(null);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setState('input');
      setCode(['', '', '', '', '', '']);
      setLoading(false);
      setErrorMessage('');
      setDeviceInfo(null);
      // Focus first input after render
      setTimeout(() => inputRefs.current[0]?.focus(), 50);
    }
  }, [open]);

  if (!open) return null;

  const userCode = code.join('');

  const handleDigitChange = (index: number, value: string) => {
    // Only accept single digit
    const digit = value.replace(/\D/g, '').slice(-1);
    const newCode = [...code];
    newCode[index] = digit;
    setCode(newCode);

    // Auto-advance to next input
    if (digit && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
    if (e.key === 'Enter' && userCode.length === 6) {
      handleVerify();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (pasted.length > 0) {
      const newCode = [...code];
      for (let i = 0; i < 6; i++) {
        newCode[i] = pasted[i] || '';
      }
      setCode(newCode);
      // Focus the input after the last pasted digit
      const focusIdx = Math.min(pasted.length, 5);
      inputRefs.current[focusIdx]?.focus();
    }
  };

  const handleVerify = async () => {
    if (userCode.length !== 6) return;
    setLoading(true);
    setErrorMessage('');

    try {
      const info = await verifyDesktopPairingCode(userCode);
      setDeviceInfo(info);
      setState('confirm');
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        setErrorMessage(t('pairing.errorInvalid'));
      } else if (status === 410) {
        setErrorMessage(t('pairing.errorExpired'));
      } else if (status === 429) {
        setErrorMessage(t('pairing.errorTooMany'));
      } else {
        setErrorMessage(t('pairing.errorGeneric'));
      }
      setState('error');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    setLoading(true);
    try {
      await approveDesktopPairingCode(userCode);
      setState('success');
      onPaired();
    } catch {
      setErrorMessage(t('pairing.errorGeneric'));
      setState('error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeny = async () => {
    setLoading(true);
    try {
      await denyDesktopPairingCode(userCode);
      toast(t('pairing.denied'), { icon: '🚫' });
      onClose();
    } catch {
      toast.error(t('pairing.errorGeneric'));
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = () => {
    setState('input');
    setCode(['', '', '', '', '', '']);
    setErrorMessage('');
    setTimeout(() => inputRefs.current[0]?.focus(), 50);
  };

  const formatExpiry = (expiresAt: string) => {
    const diff = new Date(expiresAt).getTime() - Date.now();
    const mins = Math.max(0, Math.floor(diff / 60000));
    return `${mins} min`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-lg border border-slate-800 bg-slate-900 p-5 sm:p-6 shadow-xl">
        {/* Header */}
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-emerald-500/20 p-2">
              <Monitor className="h-5 w-5 text-emerald-400" />
            </div>
            <h2 className="text-lg font-semibold text-white">
              {t('pairing.title')}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 hover:bg-slate-800 touch-manipulation active:scale-95"
          >
            <X className="h-5 w-5 text-slate-400" />
          </button>
        </div>

        {/* State: Code Input */}
        {state === 'input' && (
          <div className="space-y-5">
            <p className="text-sm text-slate-400">{t('pairing.enterCode')}</p>

            <div className="flex justify-center gap-2" onPaste={handlePaste}>
              {code.map((digit, i) => (
                <span key={i} className="contents">
                  <input
                    ref={(el) => { inputRefs.current[i] = el; }}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleDigitChange(i, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(i, e)}
                    className="h-12 w-10 rounded-lg border border-slate-700 bg-slate-900/70 text-center text-xl font-mono font-bold text-white focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                  {i === 2 && (
                    <span className="flex items-center text-slate-600 text-xl font-light select-none">
                      &ndash;
                    </span>
                  )}
                </span>
              ))}
            </div>

            <button
              onClick={handleVerify}
              disabled={userCode.length !== 6 || loading}
              className="w-full rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-200 transition hover:border-emerald-500/50 hover:bg-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed touch-manipulation active:scale-[0.98]"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('pairing.verifying')}
                </span>
              ) : (
                t('pairing.verify')
              )}
            </button>
          </div>
        )}

        {/* State: Device Confirmation */}
        {state === 'confirm' && deviceInfo && (
          <div className="space-y-5">
            <p className="text-sm text-slate-400">{t('pairing.deviceInfo')}</p>

            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 space-y-3">
              <div className="flex items-center gap-3">
                <Monitor className="h-5 w-5 text-emerald-400 flex-shrink-0" />
                <span className="text-sm font-medium text-white truncate">
                  {deviceInfo.device_name}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="text-slate-500">{t('fields.platform')}</p>
                  <p className="mt-0.5 text-slate-200">
                    {platformLabels[deviceInfo.platform] || deviceInfo.platform}
                  </p>
                </div>
                <div>
                  <p className="text-slate-500">{t('pairing.expiresIn')}</p>
                  <p className="mt-0.5 text-slate-200">
                    {formatExpiry(deviceInfo.expires_at)}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleDeny}
                disabled={loading}
                className="flex-1 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2.5 text-sm font-medium text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20 disabled:opacity-40 touch-manipulation active:scale-[0.98]"
              >
                {t('pairing.deny')}
              </button>
              <button
                onClick={handleApprove}
                disabled={loading}
                className="flex-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-200 transition hover:border-emerald-500/50 hover:bg-emerald-500/20 disabled:opacity-40 touch-manipulation active:scale-[0.98]"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('pairing.approving')}
                  </span>
                ) : (
                  t('pairing.approve')
                )}
              </button>
            </div>
          </div>
        )}

        {/* State: Success */}
        {state === 'success' && deviceInfo && (
          <div className="space-y-5 text-center">
            <div className="flex justify-center">
              <div className="rounded-full bg-emerald-500/20 p-3">
                <CheckCircle className="h-8 w-8 text-emerald-400" />
              </div>
            </div>
            <div>
              <p className="text-base font-medium text-white">
                {t('pairing.successTitle')}
              </p>
              <p className="mt-1 text-sm text-slate-400">
                {t('pairing.successMessage', { name: deviceInfo.device_name })}
              </p>
            </div>
            <button
              onClick={onClose}
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-slate-800 touch-manipulation active:scale-[0.98]"
            >
              {t('pairing.close')}
            </button>
          </div>
        )}

        {/* State: Error */}
        {state === 'error' && (
          <div className="space-y-5 text-center">
            <div className="flex justify-center">
              <div className="rounded-full bg-rose-500/20 p-3">
                <XCircle className="h-8 w-8 text-rose-400" />
              </div>
            </div>
            <div>
              <p className="text-sm text-rose-300">{errorMessage}</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="flex-1 rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-slate-800 touch-manipulation active:scale-[0.98]"
              >
                {t('pairing.close')}
              </button>
              <button
                onClick={handleRetry}
                className="flex-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-200 transition hover:border-emerald-500/50 hover:bg-emerald-500/20 touch-manipulation active:scale-[0.98]"
              >
                {t('pairing.tryAgain')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
