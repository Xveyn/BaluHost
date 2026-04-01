import { ArrowRight, SkipForward, Wifi, Bell, CloudUpload } from 'lucide-react';
import { Button } from '../ui/Button';

export interface OptionalGateProps {
  onSkipAll: () => void;
  onContinue: () => void;
}

const OPTIONAL_FEATURES = [
  {
    icon: Wifi,
    title: 'VPN-Konfiguration',
    description: 'WireGuard VPN für sicheren Fernzugriff einrichten',
  },
  {
    icon: Bell,
    title: 'Push-Benachrichtigungen',
    description: 'Firebase-Benachrichtigungen für mobile Apps konfigurieren',
  },
  {
    icon: CloudUpload,
    title: 'Cloud-Import',
    description: 'Google Drive, Dropbox oder andere Cloud-Dienste verbinden',
  },
];

export function OptionalGate({ onSkipAll, onContinue }: OptionalGateProps) {
  return (
    <div>
      <div className="text-center mb-8">
        <div className="w-16 h-16 rounded-full bg-green-600/20 flex items-center justify-center mx-auto mb-4">
          <ArrowRight className="w-8 h-8 text-green-400" />
        </div>
        <h2 className="text-xl font-semibold text-slate-100 mb-2">
          Pflichtschritte abgeschlossen
        </h2>
        <p className="text-slate-400 text-sm max-w-md mx-auto">
          Ihr NAS ist einsatzbereit. Sie können jetzt optionale Features konfigurieren
          oder direkt zum Dashboard wechseln — diese Einstellungen sind jederzeit
          erreichbar.
        </p>
      </div>

      <div className="space-y-3 mb-8">
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
          Verfügbare optionale Features
        </p>
        {OPTIONAL_FEATURES.map(({ icon: Icon, title, description }) => (
          <div
            key={title}
            className="flex items-start gap-3 px-4 py-3 rounded-lg bg-slate-800/50 border border-slate-700"
          >
            <div className="w-8 h-8 rounded-lg bg-slate-800/60 flex items-center justify-center flex-shrink-0">
              <Icon className="w-4 h-4 text-slate-300" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-100">{title}</p>
              <p className="text-xs text-slate-400">{description}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Button
          variant="secondary"
          onClick={onSkipAll}
          icon={<SkipForward className="w-4 h-4" />}
          size="lg"
          className="w-full"
        >
          Alles überspringen
        </Button>
        <Button
          onClick={onContinue}
          icon={<ArrowRight className="w-4 h-4" />}
          size="lg"
          className="w-full"
        >
          Optionale Features
        </Button>
      </div>
    </div>
  );
}
