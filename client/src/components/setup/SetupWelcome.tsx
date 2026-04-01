import { ArrowRight, FolderOpen, HardDrive, Shield, Activity, Smartphone, Clock } from 'lucide-react';
import logoMark from '../../assets/baluhost-logo.png';
import { Button } from '../ui/Button';

export interface SetupWelcomeProps {
  onStart: () => void;
}

const FEATURES = [
  { icon: FolderOpen, title: 'Dateiverwaltung', desc: 'Upload, Ordner, Freigaben & Versionierung' },
  { icon: HardDrive, title: 'RAID & Speicher', desc: 'Redundante Datensicherung mit RAID-Arrays' },
  { icon: Shield, title: 'VPN-Fernzugriff', desc: 'WireGuard-Tunnel \u2014 \u00fcberall sicher erreichbar' },
  { icon: Activity, title: 'System-Monitoring', desc: 'CPU, RAM, Netzwerk & Festplatten live' },
  { icon: Smartphone, title: 'Mobile & Desktop', desc: 'BaluApp (Android) & BaluDesk (Windows/Linux)' },
  { icon: Clock, title: 'Backups & Versionen', desc: 'Automatische Sicherung & Dateiverlauf' },
];

export function SetupWelcome({ onStart }: SetupWelcomeProps) {
  return (
    <div className="text-center">
      <div className="glow-ring h-20 w-20 mx-auto mb-6">
        <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-slate-950 p-[2px] shadow-xl">
          <img src={logoMark} alt="BaluHost logo" className="h-full w-full rounded-full" />
        </div>
      </div>

      <h2 className="text-2xl font-semibold text-slate-100 mb-2">
        Willkommen bei BaluHost
      </h2>
      <p className="text-slate-400 text-sm max-w-lg mx-auto mb-8">
        Ihr persönliches NAS-System — sicher, schnell und vollständig selbstgehostet.
        In wenigen Schritten ist Ihr System einsatzbereit.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8 text-left">
        {FEATURES.map(({ icon: Icon, title, desc }) => (
          <div
            key={title}
            className="rounded-xl border border-slate-800/60 bg-slate-800/30 p-3 backdrop-blur-sm"
          >
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 flex items-center justify-center mb-2">
              <Icon className="w-4 h-4 text-sky-400" />
            </div>
            <p className="text-sm font-medium text-slate-200">{title}</p>
            <p className="text-xs text-slate-400 mt-0.5">{desc}</p>
          </div>
        ))}
      </div>

      <Button
        onClick={onStart}
        size="lg"
        icon={<ArrowRight className="w-4 h-4" />}
        className="w-full sm:w-auto"
      >
        Einrichtung starten
      </Button>
    </div>
  );
}
