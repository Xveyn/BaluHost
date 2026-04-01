import { useState, useEffect } from 'react';
import { HardDrive, AlertTriangle, ChevronRight, Info } from 'lucide-react';
import { Button } from '../ui/Button';
import { Spinner } from '../ui/Spinner';
import { apiClient } from '../../lib/api';

export interface RaidSetupProps {
  setupToken: string;
  onComplete: () => void;
  onSkip: () => void;
}

interface RaidStatusInfo {
  arrays: Array<{
    name: string;
    level: string;
    state: string;
    size: string;
    devices: number;
  }>;
}

export function RaidSetup({ onComplete, onSkip }: RaidSetupProps) {
  const [raidStatus, setRaidStatus] = useState<RaidStatusInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState(false);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        // RAID status endpoint requires an access token, not a setup token.
        // We attempt to load it anyway for dev-mode where it might work,
        // and gracefully handle auth errors.
        const resp = await apiClient.get('/api/system/raid');
        setRaidStatus({ arrays: resp.data?.arrays ?? [] });
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 401 || status === 403) {
          setAuthError(true);
        } else {
          // Other errors — still show the UI, just no live status
          setRaidStatus({ arrays: [] });
        }
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
  }, []);

  const stateColor = (state: string) => {
    if (state === 'clean' || state === 'active') return 'text-green-400';
    if (state === 'degraded') return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-sky-500/20 flex items-center justify-center">
          <HardDrive className="w-5 h-5 text-sky-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-100">RAID-Konfiguration</h2>
          <p className="text-sm text-slate-400">
            Überprüfen Sie den aktuellen RAID-Status Ihres Systems.
          </p>
        </div>
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Spinner label="RAID-Status wird geladen..." />
        </div>
      )}

      {!loading && authError && (
        <div className="rounded-lg border border-yellow-700/50 bg-yellow-900/20 p-4 mb-5">
          <div className="flex gap-3">
            <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-yellow-300">
                RAID-Status nicht verfügbar
              </p>
              <p className="text-sm text-yellow-400/80 mt-1">
                Der RAID-Status erfordert ein vollständiges Zugangstoken. Die RAID-Verwaltung
                ist nach Abschluss des Setups im Dashboard verfügbar.
              </p>
            </div>
          </div>
        </div>
      )}

      {!loading && !authError && raidStatus && (
        <>
          {raidStatus.arrays.length === 0 ? (
            <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-5 mb-5 text-center">
              <HardDrive className="w-10 h-10 text-slate-500 mx-auto mb-3" />
              <p className="text-sm text-slate-400">
                Keine RAID-Arrays konfiguriert.
              </p>
              <p className="text-xs text-slate-500 mt-1">
                Sie können RAID-Arrays nach dem Setup im RAID-Management-Bereich erstellen.
              </p>
            </div>
          ) : (
            <div className="space-y-3 mb-5">
              {raidStatus.arrays.map((array) => (
                <div
                  key={array.name}
                  className="flex items-center justify-between px-4 py-3 bg-slate-800/40 rounded-lg border border-slate-700"
                >
                  <div className="flex items-center gap-3">
                    <HardDrive className="w-4 h-4 text-slate-400" />
                    <div>
                      <p className="text-sm font-medium text-slate-100">{array.name}</p>
                      <p className="text-xs text-slate-400">
                        {array.level.toUpperCase()} &middot; {array.devices} Disks &middot; {array.size}
                      </p>
                    </div>
                  </div>
                  <span className={`text-xs font-medium capitalize ${stateColor(array.state)}`}>
                    {array.state}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <div className="rounded-lg border border-sky-800/50 bg-sky-900/10 p-4 mb-6">
        <div className="flex gap-3">
          <Info className="w-4 h-4 text-sky-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-sky-300/80">
            Die vollständige RAID-Verwaltung (Arrays erstellen, verwalten, Festplatten hinzufügen)
            ist nach dem Setup im Bereich <strong className="text-sky-300">RAID-Management</strong> verfügbar.
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
