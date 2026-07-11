import { Router } from 'lucide-react';
import { Toggle } from './SleepFormControls';
import type { FritzBoxForm } from '../../../hooks/useFritzBoxForm';
import type { FritzBoxConfig } from '../../../api/fritzbox';
import type { SleepCapabilities } from '../../../api/sleep';

type FritzBoxCardProps = FritzBoxForm & {
  update: (patch: Partial<FritzBoxForm>) => void;
  config: FritzBoxConfig | null;
  testing: boolean;
  onTest: () => void;
  capabilities: SleepCapabilities | null;
};

export function FritzBoxCard({
  host, port, username, password, mac, enabled, update, config, testing, onTest, capabilities,
}: FritzBoxCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
      <h4 className="text-sm font-medium text-white flex items-center gap-2">
        <Router className="h-4 w-4 text-orange-400" />
        Fritz!Box WoL
        <span className="ml-auto">
          <Toggle checked={enabled} onChange={(v) => update({ enabled: v })} />
        </span>
      </h4>
      {enabled && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Host</label>
              <input
                type="text"
                value={host}
                onChange={(e) => update({ host: e.target.value })}
                placeholder="192.168.178.1"
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Port</label>
              <input
                type="number"
                value={port}
                onChange={(e) => update({ port: Number(e.target.value) })}
                placeholder="49000"
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => update({ username: e.target.value })}
                placeholder="(often empty)"
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Password {config?.has_password && <span className="text-teal-400">(set)</span>}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => update({ password: e.target.value })}
                placeholder={config?.has_password ? '••••••••' : 'TR-064 Password'}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">NAS MAC Address</label>
            <input
              type="text"
              value={mac}
              onChange={(e) => update({ mac: e.target.value })}
              placeholder="AA:BB:CC:DD:EE:FF"
              className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
            />
            {capabilities?.own_mac_address && capabilities.own_mac_address !== mac && (
              <button
                type="button"
                onClick={() => update({ mac: capabilities.own_mac_address! })}
                className="mt-1.5 text-xs text-teal-400 hover:text-teal-300 transition-colors"
              >
                Erkannt: <span className="font-mono">{capabilities.own_mac_address}</span> — Übernehmen?
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={onTest}
            disabled={testing}
            className="rounded-lg bg-orange-500/20 px-4 py-2 text-sm font-medium text-orange-300 hover:bg-orange-500/30 transition-colors disabled:opacity-50"
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
        </div>
      )}
    </div>
  );
}
