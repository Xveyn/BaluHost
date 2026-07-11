import { Smartphone, RefreshCw } from 'lucide-react';
import type { MobileDevice } from '../../api/mobile';
import { MobileDeviceCard } from './MobileDeviceCard';

interface MobileDevicesListProps {
  devices: MobileDevice[];
  loading: boolean;
  isFetching: boolean;
  isAdmin: boolean;
  onRefresh: () => void;
  onShowQr: (device: MobileDevice) => void;
  onDelete: (id: string, name: string) => void;
}

export function MobileDevicesList({ devices, loading, isFetching, isAdmin, onRefresh, onShowQr, onDelete }: MobileDevicesListProps) {
  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center">
          <Smartphone className="w-5 h-5 mr-2 text-sky-400" />
          Registrierte Geräte ({devices.length})
        </h3>
        <button
          onClick={onRefresh}
          disabled={isFetching}
          className="p-2 text-slate-400 hover:text-white transition-colors touch-manipulation active:scale-95 min-w-[44px] min-h-[44px] flex items-center justify-center"
          title="Aktualisieren"
        >
          <RefreshCw className={`w-5 h-5 ${isFetching ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading ? (
        <div className="text-center py-8 text-slate-400">
          <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-2" />
          Lade Geräte...
        </div>
      ) : devices.length === 0 ? (
        <div className="text-center py-8 text-slate-400">
          <Smartphone className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>Keine Geräte registriert</p>
          <p className="text-sm mt-1">Generiere einen QR-Code, um dein erstes Gerät hinzuzufügen</p>
        </div>
      ) : (
        <div className="space-y-3">
          {devices.map((device) => (
            <MobileDeviceCard key={device.id} device={device} isAdmin={isAdmin} onShowQr={onShowQr} onDelete={onDelete} />
          ))}
        </div>
      )}
    </div>
  );
}
