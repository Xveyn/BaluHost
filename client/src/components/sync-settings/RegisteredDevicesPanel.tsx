import { Smartphone } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { SyncDevice, SyncFolderItem } from '../../api/sync';

interface RegisteredDevicesPanelProps {
  devices: SyncDevice[];
  deviceFolders: Record<string, SyncFolderItem[]>;
  onRevokeVpn: (clientId: number) => Promise<void>;
}

function formatDate(date: string | null) {
  if (!date) return 'N/A';
  return new Date(date).toLocaleString('de-DE');
}

export function RegisteredDevicesPanel({ devices, deviceFolders, onRevokeVpn }: RegisteredDevicesPanelProps) {
  const { t } = useTranslation('settings');

  return (
    <div className="rounded-lg shadow bg-slate-900/55 p-6">
      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <Smartphone className="w-5 h-5" />
        {t('sync.registeredDevices')}
      </h3>
      {devices.length === 0 ? (
        <div className="text-slate-400 text-center py-6">{t('sync.noDevices')}</div>
      ) : (
        <div className="space-y-3">
          {devices.map((d) => (
            <div key={d.device_id} className="p-4 bg-slate-800/50 border border-slate-700 rounded-lg">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-slate-200">
                    {d.device_name}
                    <span className="text-xs text-slate-400 ml-2">({d.device_id.substring(0, 8)}...)</span>
                  </div>
                  <div className="text-xs text-slate-500">
                    {t('sync.status')}: {d.status} | {t('sync.lastSync')}: {formatDate(d.last_sync)}
                  </div>
                </div>
                <div className="text-right">
                  {d.vpn_client_id ? (
                    <div className="text-xs text-slate-300">
                      <div className="flex items-center gap-3">
                        <div>{t('sync.vpn')}: <span className="font-medium text-sky-300">{d.vpn_assigned_ip ?? `client ${d.vpn_client_id}`}</span></div>
                        <button
                          onClick={() => onRevokeVpn(d.vpn_client_id!)}
                          className="px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white text-xs rounded transition-colors"
                        >
                          {t('sync.revokeVpn')}
                        </button>
                      </div>
                      <div className="text-xs text-slate-500">
                        {t('sync.lastHandshake')}: {d.vpn_last_handshake ? formatDate(d.vpn_last_handshake) : 'N/A'}
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-slate-400">{t('sync.noVpnConfigured')}</div>
                  )}
                </div>
              </div>
              {/* Per-device sync folders */}
              <div className="mt-3 border-t border-slate-700 pt-3">
                <div className="text-sm text-slate-400 mb-2">{t('sync.syncFolders')}</div>
                {deviceFolders[d.device_id] && deviceFolders[d.device_id].length > 0 ? (
                  <div className="space-y-2">
                    {deviceFolders[d.device_id].map((f) => (
                      <div key={f.id} className="p-2 bg-slate-800/40 border border-slate-700 rounded-lg text-xs">
                        <div className="font-medium text-slate-200">{f.local_path} → {f.remote_path}</div>
                        <div className="text-slate-400 text-xs mt-1">
                          Type: {f.sync_type} | Auto: {f.auto_sync ? 'yes' : 'no'} | Status: {f.status ?? 'N/A'}
                        </div>
                        <div className="text-slate-500 text-xs">Last sync: {formatDate(f.last_sync ?? null)}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500">No sync folders configured for this device</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
