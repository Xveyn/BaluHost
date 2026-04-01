import { Shield, ChevronRight, Info, Lock, Wifi } from 'lucide-react';
import { Button } from '../ui/Button';
import type { OptionalStepProps } from './SharingSetup';

const FEATURES = [
  { icon: Lock, text: 'Verschlüsselter Tunnel per WireGuard' },
  { icon: Wifi, text: 'Zugriff auf Ihr NAS von überall' },
];

export function VpnSetup({ onComplete, onSkip }: OptionalStepProps) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-purple-600/20 flex items-center justify-center">
          <Shield className="w-5 h-5 text-purple-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-100">WireGuard VPN</h2>
          <p className="text-sm text-slate-400">Sicherer Fernzugriff auf Ihr NAS</p>
        </div>
      </div>

      <p className="text-sm text-slate-300 mb-5">
        Mit dem integrierten WireGuard-VPN können Sie von überall sicher auf Ihr NAS zugreifen.
        Jeder Client erhält ein eigenes Schlüsselpaar und eine QR-Code-Konfiguration zur einfachen
        Einrichtung auf Smartphones oder Desktops.
      </p>

      <div className="space-y-2 mb-5">
        {FEATURES.map(({ icon: Icon, text }) => (
          <div
            key={text}
            className="flex items-center gap-3 px-4 py-3 rounded-lg bg-slate-800/40 border border-slate-700"
          >
            <Icon className="w-4 h-4 text-purple-400 flex-shrink-0" />
            <p className="text-sm text-slate-300">{text}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-sky-800/50 bg-sky-900/10 p-4 mb-6">
        <div className="flex gap-3">
          <Info className="w-4 h-4 text-sky-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-sky-300/80">
            Die VPN-Konfiguration (Clients hinzufügen, Schlüssel verwalten) erfolgt nach dem Setup
            im Bereich <strong className="text-sky-300">VPN</strong>. Für den Betrieb muss
            WireGuard auf dem Server installiert sein.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t border-slate-700 flex justify-between">
        <Button variant="ghost" onClick={onSkip}>
          Überspringen
        </Button>
        <Button onClick={onComplete} icon={<ChevronRight className="w-4 h-4" />} size="lg">
          Weiter
        </Button>
      </div>
    </div>
  );
}
