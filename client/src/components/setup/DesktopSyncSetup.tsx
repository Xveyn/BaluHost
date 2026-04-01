import { Monitor, ChevronRight, Info, Download } from 'lucide-react';
import { Button } from '../ui/Button';
import type { OptionalStepProps } from './SharingSetup';

export function DesktopSyncSetup({ onComplete, onSkip }: OptionalStepProps) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-green-600/20 flex items-center justify-center">
          <Monitor className="w-5 h-5 text-green-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">BaluDesk – Desktop-Sync</h2>
          <p className="text-sm text-gray-400">Automatische Synchronisierung für Windows & Linux</p>
        </div>
      </div>

      <p className="text-sm text-gray-300 mb-5">
        Mit BaluDesk synchronisieren Sie Ordner auf Ihrem PC automatisch mit dem NAS.
        Der Desktop-Client läuft im Hintergrund, erkennt Änderungen in Echtzeit und überträgt
        diese bidirektional — ähnlich wie Dropbox, aber auf Ihrer eigenen Hardware.
      </p>

      <div className="px-4 py-3 rounded-lg bg-gray-700/40 border border-gray-700 mb-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-white">BaluDesk herunterladen</p>
            <p className="text-xs text-gray-400">Windows &amp; Linux – kostenlos</p>
          </div>
          <a
            href="https://github.com/Xveyn/BaluDesk/releases"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-600/20 border border-green-700/50 text-green-300 text-xs font-medium hover:bg-green-600/30 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            GitHub Releases
          </a>
        </div>
      </div>

      <div className="rounded-lg border border-blue-800/50 bg-blue-900/10 p-4 mb-6">
        <div className="flex gap-3">
          <Info className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-blue-300/80">
            Nach der Installation verbindet sich BaluDesk automatisch über die{' '}
            <strong className="text-blue-300">Gerätekopplung</strong> mit Ihrem NAS.
            Sync-Ordner werden dann im Bereich <strong className="text-blue-300">Geräte</strong>{' '}
            verwaltet.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t border-gray-700 flex justify-between">
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
