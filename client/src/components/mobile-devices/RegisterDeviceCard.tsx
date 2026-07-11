import { QrCode as QrCodeIcon, RefreshCw, Plus } from 'lucide-react';

interface RegisterDeviceCardProps {
  deviceName: string;
  onDeviceNameChange: (v: string) => void;
  tokenValidityDays: number;
  onValidityChange: (v: number) => void;
  includeVpn: boolean;
  onIncludeVpnChange: (v: boolean) => void;
  vpnType: string;
  onVpnTypeChange: (v: string) => void;
  availableVpnTypes: string[];
  generating: boolean;
  onGenerate: () => void;
}

export function RegisterDeviceCard({
  deviceName,
  onDeviceNameChange,
  tokenValidityDays,
  onValidityChange,
  includeVpn,
  onIncludeVpnChange,
  vpnType,
  onVpnTypeChange,
  availableVpnTypes,
  generating,
  onGenerate,
}: RegisterDeviceCardProps) {
  return (
    <div className="card border-slate-800/60 bg-slate-900/55 mb-6">
      <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
        <QrCodeIcon className="w-5 h-5 mr-2 text-sky-400" />
        Neues Gerät registrieren
      </h3>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Gerätename
          </label>
          <input
            type="text"
            value={deviceName}
            onChange={(e) => onDeviceNameChange(e.target.value)}
            placeholder="z.B. iPhone 15, Samsung Galaxy S24"
            className="input w-full"
          />
        </div>

        {/* Token Validity Slider */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Gültigkeitsdauer der Autorisierung
          </label>
          <div className="space-y-2">
            <input
              type="range"
              min="30"
              max="180"
              step="1"
              value={tokenValidityDays}
              onChange={(e) => onValidityChange(Number(e.target.value))}
              className="w-full h-3 sm:h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer slider-thumb touch-manipulation"
              style={{
                background: `linear-gradient(to right, #38bdf8 0%, #38bdf8 ${((tokenValidityDays - 30) / 150) * 100}%, #334155 ${((tokenValidityDays - 30) / 150) * 100}%, #334155 100%)`
              }}
            />
            <div className="flex flex-col sm:flex-row items-center justify-between gap-1 sm:gap-2 text-xs">
              <span className="text-slate-400 hidden sm:inline">30 Tage</span>
              <span className="text-sky-400 font-semibold text-sm sm:text-base">
                {tokenValidityDays} Tage ({Math.round(tokenValidityDays / 30)} Monate)
              </span>
              <span className="text-slate-400 hidden sm:inline">180 Tage</span>
              <span className="text-slate-400 sm:hidden text-[10px]">30 - 180 Tage</span>
            </div>
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-2 sm:p-3">
              <p className="text-[10px] sm:text-xs text-slate-400">
                🔔 <strong>Auto-Erinnerungen:</strong> <span className="hidden sm:inline">Du wirst </span><strong>7 Tage</strong>, <strong>3 Tage</strong> & <strong>1 Stunde</strong> vor Ablauf benachrichtigt.
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="includeVpn"
              checked={includeVpn}
              onChange={(e) => onIncludeVpnChange(e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-sky-500 focus:ring-sky-500"
            />
            <label htmlFor="includeVpn" className="text-sm text-slate-300">
              VPN-Konfiguration einschließen (WireGuard)
            </label>
          </div>

          {includeVpn && availableVpnTypes.length === 1 && availableVpnTypes[0] === 'wireguard' && (
            <div className="ml-6 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
              <p className="text-xs text-amber-300">
                ⚠ Kein Router-VPN konfiguriert. VPN wird direkt ueber das NAS bereitgestellt. Bei Nutzung von Sleep/WoL ist der VPN-Tunnel nicht erreichbar, solange das NAS schlaeft.
              </p>
            </div>
          )}

          {includeVpn && availableVpnTypes.length > 1 && (
            <div className="ml-6 space-y-2">
              <label className="block text-sm font-medium text-slate-300">
                VPN-Typ
              </label>
              <div className="flex flex-wrap gap-2">
                {[
                  { value: 'auto', label: 'Automatisch' },
                  ...(availableVpnTypes.includes('fritzbox') ? [{ value: 'fritzbox', label: 'Router-VPN (FritzBox)' }] : []),
                  { value: 'wireguard', label: 'NAS-VPN (WireGuard)' },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => onVpnTypeChange(opt.value)}
                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                      vpnType === opt.value
                        ? 'border-sky-500 bg-sky-500/20 text-sky-300'
                        : 'border-slate-700 bg-slate-800 text-slate-400 hover:border-slate-600'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-slate-500">
                {vpnType === 'auto' && 'Router-VPN bevorzugt, NAS-VPN als Fallback'}
                {vpnType === 'fritzbox' && 'Nutzt die vom Admin hochgeladene Router-Konfiguration'}
                {vpnType === 'wireguard' && 'VPN laeuft direkt ueber das NAS'}
              </p>
              {vpnType === 'wireguard' && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                  <p className="text-xs text-amber-300">
                    ⚠ VPN laeuft direkt ueber das NAS. Bei Nutzung von Sleep/WoL ist der VPN-Tunnel nicht erreichbar, solange das NAS schlaeft.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
        <button
          onClick={onGenerate}
          disabled={generating || !deviceName.trim()}
          className="w-full sm:w-auto px-6 py-2.5 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 touch-manipulation active:scale-95 min-h-[44px]"
        >
          {generating ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              Generiere...
            </>
          ) : (
            <>
              <Plus className="w-4 h-4" />
              QR-Code generieren
            </>
          )}
        </button>
      </div>
    </div>
  );
}
