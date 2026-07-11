import { Wifi } from 'lucide-react';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';
import type { SleepCapabilities } from '../../../api/sleep';

type WolCardProps = Pick<SleepConfigForm, 'wolMac' | 'wolBroadcast'> & {
  update: (patch: Partial<SleepConfigForm>) => void;
  capabilities: SleepCapabilities | null;
};

export function WolCard({ wolMac, wolBroadcast, update, capabilities }: WolCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
      <h4 className="text-sm font-medium text-white flex items-center gap-2">
        <Wifi className="h-4 w-4 text-amber-400" />
        Wake-on-LAN
      </h4>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">MAC Address</label>
          <input
            type="text"
            value={wolMac}
            onChange={(e) => update({ wolMac: e.target.value })}
            placeholder="AA:BB:CC:DD:EE:FF"
            className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
          />
          {capabilities?.own_mac_address && capabilities.own_mac_address !== wolMac && (
            <button
              type="button"
              onClick={() => update({ wolMac: capabilities.own_mac_address! })}
              className="mt-1.5 text-xs text-teal-400 hover:text-teal-300 transition-colors"
            >
              Erkannt: <span className="font-mono">{capabilities.own_mac_address}</span> — Übernehmen?
            </button>
          )}
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Broadcast Address</label>
          <input
            type="text"
            value={wolBroadcast}
            onChange={(e) => update({ wolBroadcast: e.target.value })}
            placeholder="255.255.255.255"
            className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
          />
        </div>
      </div>
    </div>
  );
}
