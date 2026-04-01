import { Cloud, ChevronRight, Info } from 'lucide-react';
import { Button } from '../ui/Button';
import type { OptionalStepProps } from './SharingSetup';

const SUPPORTED_PROVIDERS = ['Google Drive', 'Dropbox', 'OneDrive', 'S3', 'und mehr'];

export function CloudImportSetup({ onComplete, onSkip }: OptionalStepProps) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-cyan-600/20 flex items-center justify-center">
          <Cloud className="w-5 h-5 text-cyan-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Cloud-Import</h2>
          <p className="text-sm text-slate-400">Daten aus Cloud-Diensten importieren</p>
        </div>
      </div>

      <p className="text-sm text-slate-300 mb-5">
        Mit dem Cloud-Import können Sie Dateien aus externen Diensten direkt auf Ihr NAS übertragen.
        Die Integration basiert auf rclone und unterstützt alle gängigen Cloud-Anbieter.
        Kopieren, verschieben oder synchronisieren Sie Ihre Daten komfortabel im Browser.
      </p>

      <div className="mb-5">
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
          Unterstützte Dienste
        </p>
        <div className="flex flex-wrap gap-2">
          {SUPPORTED_PROVIDERS.map((provider) => (
            <span
              key={provider}
              className="px-3 py-1 rounded-full text-xs font-medium bg-slate-800/60 text-slate-300 border border-slate-600"
            >
              {provider}
            </span>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-sky-800/50 bg-sky-900/10 p-4 mb-6">
        <div className="flex gap-3">
          <Info className="w-4 h-4 text-sky-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-sky-300/80">
            Cloud-Remotes werden nach dem Setup im Bereich{' '}
            <strong className="text-sky-300">Cloud-Import</strong> eingerichtet. Dafür muss
            rclone auf dem Server installiert sein.
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
