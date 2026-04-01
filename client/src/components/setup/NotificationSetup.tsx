import { Bell, ChevronRight, Info, AlertCircle } from 'lucide-react';
import { Button } from '../ui/Button';
import type { OptionalStepProps } from './SharingSetup';

export function NotificationSetup({ onComplete, onSkip }: OptionalStepProps) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-yellow-600/20 flex items-center justify-center">
          <Bell className="w-5 h-5 text-yellow-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Push-Benachrichtigungen</h2>
          <p className="text-sm text-slate-400">Firebase-Benachrichtigungen für mobile Apps</p>
        </div>
      </div>

      <p className="text-sm text-slate-300 mb-5">
        BaluHost kann Push-Benachrichtigungen an die BaluApp senden — etwa bei neuen Uploads,
        abgeschlossenen Backups oder Systemwarnungen. Dafür wird ein Firebase-Projekt mit einem
        Service-Account-Schlüssel benötigt.
      </p>

      <div className="rounded-lg border border-yellow-800/50 bg-yellow-900/10 p-4 mb-5">
        <div className="flex gap-3">
          <AlertCircle className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-yellow-300">Firebase-Konto erforderlich</p>
            <p className="text-sm text-yellow-400/80 mt-1">
              Für Push-Benachrichtigungen benötigen Sie ein Google Firebase-Projekt und einen
              FCM-Service-Account-Schlüssel (JSON-Datei).
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-sky-800/50 bg-sky-900/10 p-4 mb-6">
        <div className="flex gap-3">
          <Info className="w-4 h-4 text-sky-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-sky-300/80">
            Den Firebase-Schlüssel können Sie nach dem Setup unter{' '}
            <strong className="text-sky-300">Einstellungen → Benachrichtigungen</strong> hochladen
            und konfigurieren.
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
