import { Smartphone, ChevronRight, Info, Download, QrCode } from 'lucide-react';
import { Button } from '../ui/Button';
import type { OptionalStepProps } from './SharingSetup';

export function MobileAppSetup({ onComplete, onSkip }: OptionalStepProps) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-indigo-600/20 flex items-center justify-center">
          <Smartphone className="w-5 h-5 text-indigo-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">BaluApp – Mobile App</h2>
          <p className="text-sm text-gray-400">Android-App für unterwegs</p>
        </div>
      </div>

      <p className="text-sm text-gray-300 mb-5">
        Die BaluApp ermöglicht den Zugriff auf Ihr NAS direkt vom Smartphone. Dateien hochladen,
        herunterladen und verwalten, Push-Benachrichtigungen empfangen und den Systemstatus
        im Blick behalten — alles in einer nativen Android-App.
      </p>

      <div className="space-y-2 mb-5">
        <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-gray-700/40 border border-gray-700">
          <QrCode className="w-4 h-4 text-indigo-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-white">QR-Code-Kopplung</p>
            <p className="text-xs text-gray-400">
              Gerät über QR-Code in Sekunden verbinden (inklusive VPN-Profil)
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-gray-700/40 border border-gray-700">
          <div>
            <p className="text-sm font-medium text-white">BaluApp herunterladen</p>
            <p className="text-xs text-gray-400">Android – kostenlos</p>
          </div>
          <a
            href="https://github.com/Xveyn/BaluApp/releases"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 border border-indigo-700/50 text-indigo-300 text-xs font-medium hover:bg-indigo-600/30 transition-colors"
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
            Nach der Installation scannen Sie den Kopplungs-QR-Code unter{' '}
            <strong className="text-blue-300">Mobile Geräte</strong>. Das Gerät erhält
            automatisch ein 30-Tage-Token und optional ein VPN-Profil.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t border-gray-700 flex justify-between">
        <Button variant="ghost" onClick={onSkip}>
          Überspringen
        </Button>
        <Button onClick={onComplete} icon={<ChevronRight className="w-4 h-4" />} size="lg">
          Fertig
        </Button>
      </div>
    </div>
  );
}
