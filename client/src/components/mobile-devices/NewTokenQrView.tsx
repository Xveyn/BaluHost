import toast from 'react-hot-toast';
import { Eye, EyeOff, Copy } from 'lucide-react';
import type { MobileRegistrationToken } from '../../api/mobile';

interface NewTokenQrViewProps {
  qrData: MobileRegistrationToken;
  showToken: boolean;
  onToggleToken: () => void;
}

export function NewTokenQrView({ qrData, showToken, onToggleToken }: NewTokenQrViewProps) {
  return (
    <>
      <div className="bg-white p-4 rounded-lg mb-4">
        <img
          src={`data:${qrData.qr_code.startsWith('iVBOR') ? 'image/png' : 'image/svg+xml'};base64,${qrData.qr_code}`}
          alt="QR Code"
          className="w-full h-auto"
        />
      </div>

      <button
        onClick={onToggleToken}
        className="w-full text-xs text-slate-400 hover:text-sky-400 transition-colors py-1.5 flex items-center justify-center gap-1.5 mb-3"
      >
        {showToken ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
        {showToken ? 'Token verbergen' : 'Token manuell anzeigen'}
      </button>
      {showToken && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3 mb-4">
          <p className="text-xs text-slate-400 mb-1">Registrierungs-Token:</p>
          <div className="flex items-center gap-2">
            <code className="text-sm text-white font-mono break-all flex-1">{qrData.token}</code>
            <button
              onClick={() => {
                navigator.clipboard.writeText(qrData.token);
                toast.success('Token kopiert');
              }}
              title="Kopieren"
              className="text-slate-400 hover:text-sky-400 transition-colors p-1 flex-shrink-0"
            >
              <Copy className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <div className="space-y-2 text-sm text-slate-300 mb-4">
        <p>✓ Scanne diesen QR-Code mit der BaluHost Mobile App</p>
        <p>✓ Registrierungs-Token ist <strong>5 Minuten</strong> gültig</p>
        <p>✓ Geräte-Autorisierung gilt für <strong className="text-sky-400">{qrData.device_token_validity_days} Tage ({Math.round(qrData.device_token_validity_days / 30)} Monate)</strong></p>
        {qrData.vpn_config && (
          <p className="text-green-400">✓ VPN-Konfiguration eingeschlossen</p>
        )}
        {qrData.vpn_fallback && (
          <div className="p-2 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <p className="text-xs text-amber-300">
              ⚠ Kein Router-VPN konfiguriert — NAS-VPN wird als Fallback verwendet.
            </p>
          </div>
        )}
      </div>

      <div className="bg-sky-500/10 border border-sky-500/30 rounded-lg p-3 mb-4">
        <p className="text-xs text-sky-300 font-semibold mb-1.5 flex items-center gap-1.5">
          🔔 Automatische Erinnerungen
        </p>
        <p className="text-xs text-slate-300">
          Du wirst <strong>7 Tage</strong>, <strong>3 Tage</strong> und <strong>1 Stunde</strong> vor Ablauf per Push-Benachrichtigung erinnert.
        </p>
      </div>

      <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
        <p className="text-xs text-slate-400 mb-1">Token läuft ab:</p>
        <p className="text-sm text-white font-mono">
          {new Date(qrData.expires_at).toLocaleString('de-DE')}
        </p>
      </div>
    </>
  );
}
