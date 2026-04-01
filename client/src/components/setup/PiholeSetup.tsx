import { useState } from 'react';
import { Globe, ChevronRight, Info } from 'lucide-react';
import { Button } from '../ui/Button';
import type { OptionalStepProps } from './SharingSetup';

export function PiholeSetup({ onComplete, onSkip }: OptionalStepProps) {
  const [enabled, setEnabled] = useState(false);

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-red-600/20 flex items-center justify-center">
          <Globe className="w-5 h-5 text-red-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">Pi-hole DNS</h2>
          <p className="text-sm text-gray-400">Netzwerkweite Werbeblockierung</p>
        </div>
      </div>

      <p className="text-sm text-gray-300 mb-5">
        BaluHost kann sich mit einem Pi-hole-DNS-Server verbinden und dessen Statistiken direkt
        im Dashboard anzeigen. Sie sehen blockierte Anfragen, Top-Domains und können Sperrlisten
        verwalten — ohne die Pi-hole-Weboberfläche zu öffnen.
      </p>

      <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-gray-700/40 border border-gray-700 mb-5">
        <div>
          <p className="text-sm font-medium text-white">Pi-hole-Integration aktivieren</p>
          <p className="text-xs text-gray-400">Verbindet BaluHost mit einem Pi-hole-Server</p>
        </div>
        <button
          type="button"
          onClick={() => setEnabled((v) => !v)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            enabled ? 'bg-red-600' : 'bg-gray-600'
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              enabled ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      </div>

      <div className="rounded-lg border border-blue-800/50 bg-blue-900/10 p-4 mb-6">
        <div className="flex gap-3">
          <Info className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-blue-300/80">
            Die Pi-hole-Adresse und den API-Token konfigurieren Sie nach dem Setup unter{' '}
            <strong className="text-blue-300">Pi-hole</strong>. Pi-hole muss separat installiert
            und betrieben werden.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t border-gray-700 flex justify-between">
        <Button variant="ghost" onClick={onSkip}>
          Überspringen
        </Button>
        <Button onClick={onComplete} icon={<ChevronRight className="w-4 h-4" />} size="lg">
          Aktivieren
        </Button>
      </div>
    </div>
  );
}
