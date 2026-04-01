import { useState, useEffect } from 'react';
import { Wifi } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../lib/api';
import { useVPNProfiles } from '../hooks/useRemoteServers';
import { VPNProfileList } from './RemoteServers/VPNProfileList';
import { VPNProfileForm } from './RemoteServers/VPNProfileForm';

export default function VpnManagement() {
  const { t } = useTranslation('settings');
  const vpnProfiles = useVPNProfiles();
  const [nasVpnInfo, setNasVpnInfo] = useState<{ configured: boolean; activeClients: number } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadNasVpnStatus();
  }, []);

  const loadNasVpnStatus = async () => {
    try {
      setLoading(true);
      const serverRes = await apiClient.get('/api/vpn/server-config');
      setNasVpnInfo({
        configured: true,
        activeClients: serverRes.data.active_clients ?? 0,
      });
    } catch {
      setNasVpnInfo({ configured: false, activeClients: 0 });
    } finally {
      setLoading(false);
    }
  };

  if (loading && vpnProfiles.loading) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500 mx-auto"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* VPN Profiles Section */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">VPN Profiles</h3>
          <VPNProfileForm
            onCreateProfile={vpnProfiles.createProfile}
            isLoading={vpnProfiles.loading}
          />
        </div>

        {vpnProfiles.error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300">
            {vpnProfiles.error}
          </div>
        )}

        <VPNProfileList
          profiles={vpnProfiles.profiles}
          isLoading={vpnProfiles.loading}
          onDelete={vpnProfiles.deleteProfile}
          onTestConnection={vpnProfiles.testConnection}
        />
      </div>

      {/* NAS VPN Server Info */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
          <Wifi className="w-5 h-5 mr-2 text-slate-400" />
          {t('vpn.nasVpnTitle')}
        </h3>

        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg mb-4">
          <p className="text-xs text-amber-300">
            {t('vpn.nasVpnWolWarning')}
          </p>
        </div>

        {nasVpnInfo && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-slate-400">{t('vpn.status')}:</span>
              <p className={`font-medium ${nasVpnInfo.configured ? 'text-green-400' : 'text-slate-400'}`}>
                {nasVpnInfo.configured ? t('vpn.nasVpnInitialized') : t('vpn.nasVpnNotInitialized')}
              </p>
            </div>
            {nasVpnInfo.configured && (
              <div>
                <span className="text-slate-400">{t('vpn.nasVpnActiveClients')}:</span>
                <p className="text-white font-medium">{nasVpnInfo.activeClients}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
