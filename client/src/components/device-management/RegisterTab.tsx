import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { QrCode as QrCodeIcon, Plus, RefreshCw } from 'lucide-react';
import type { MobileRegistrationToken } from '../../lib/api';

interface RegisterTabProps {
  onGenerate: (name: string, includeVpn: boolean, validityDays: number) => Promise<MobileRegistrationToken | null>;
  onTokenGenerated: (token: MobileRegistrationToken) => void;
}

export function RegisterTab({ onGenerate, onTokenGenerated }: RegisterTabProps) {
  const { t } = useTranslation(['devices']);
  const [deviceName, setDeviceName] = useState('');
  const [validityDays, setValidityDays] = useState(90);
  const [includeVpn, setIncludeVpn] = useState(false);
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const token = await onGenerate(deviceName, includeVpn, validityDays);
      if (token) {
        onTokenGenerated(token);
        setDeviceName('');
        setIncludeVpn(false);
      }
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
        <QrCodeIcon className="w-5 h-5 mr-2 text-sky-400" />
        {t('register.title')}
      </h3>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            {t('register.deviceName')}
          </label>
          <input
            type="text"
            value={deviceName}
            onChange={(e) => setDeviceName(e.target.value)}
            placeholder={t('register.deviceNamePlaceholder')}
            className="input w-full"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            {t('register.validity')}
          </label>
          <div className="space-y-2">
            <input
              type="range"
              min="30"
              max="180"
              step="1"
              value={validityDays}
              onChange={(e) => setValidityDays(Number(e.target.value))}
              className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer"
              style={{
                background: `linear-gradient(to right, #38bdf8 0%, #38bdf8 ${((validityDays - 30) / 150) * 100}%, #334155 ${((validityDays - 30) / 150) * 100}%, #334155 100%)`,
              }}
            />
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">{t('register.validityMin')}</span>
              <span className="text-sky-400 font-semibold text-base">
                {t('register.validityDisplay', { days: validityDays, months: Math.round(validityDays / 30) })}
              </span>
              <span className="text-slate-400">{t('register.validityMax')}</span>
            </div>
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">
                🔔 <strong>{t('register.notifications')}:</strong> {t('register.notificationsDesc')}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="includeVpn"
            checked={includeVpn}
            onChange={(e) => setIncludeVpn(e.target.checked)}
            className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-sky-500 focus:ring-sky-500"
          />
          <label htmlFor="includeVpn" className="text-sm text-slate-300">
            {t('register.includeVpn')}
          </label>
        </div>

        <button
          onClick={handleGenerate}
          disabled={generating || !deviceName.trim()}
          className="w-full sm:w-auto px-6 py-2.5 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {generating ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              {t('register.generating')}
            </>
          ) : (
            <>
              <Plus className="w-4 h-4" />
              {t('register.generateQr')}
            </>
          )}
        </button>
      </div>
    </div>
  );
}
