import { useState } from 'react';
import { Share2, ChevronRight, Info } from 'lucide-react';
import { Button } from '../ui/Button';

export interface OptionalStepProps {
  setupToken: string;
  onComplete: () => void;
  onSkip: () => void;
}

export function SharingSetup({ onComplete, onSkip }: OptionalStepProps) {
  const [enabled, setEnabled] = useState(true);

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-blue-600/20 flex items-center justify-center">
          <Share2 className="w-5 h-5 text-blue-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">Dateifreigabe</h2>
          <p className="text-sm text-gray-400">Dateien und Ordner mit anderen teilen</p>
        </div>
      </div>

      <p className="text-sm text-gray-300 mb-5">
        Mit der Freigabe-Funktion können Sie Dateien über sichere Links mit anderen teilen —
        auch ohne BaluHost-Konto. Sie können Ablaufzeiten, Passwörter und Zugriffsrechte
        für jeden Link individuell festlegen.
      </p>

      <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-gray-700/40 border border-gray-700 mb-5">
        <div>
          <p className="text-sm font-medium text-white">Dateifreigabe aktivieren</p>
          <p className="text-xs text-gray-400">Ermöglicht das Erstellen von Freigabe-Links</p>
        </div>
        <button
          type="button"
          onClick={() => setEnabled((v) => !v)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            enabled ? 'bg-blue-600' : 'bg-gray-600'
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
            Freigabe-Links und deren Berechtigungen können jederzeit im Bereich{' '}
            <strong className="text-blue-300">Freigaben</strong> verwaltet werden.
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
