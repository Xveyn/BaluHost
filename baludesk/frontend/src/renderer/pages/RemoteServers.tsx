import { useState } from 'react';
import { useRemoteServerProfiles } from '../hooks/useRemoteServerProfiles';
import { useVPNProfiles } from '../hooks/useVPNProfiles';
import { ServerProfileForm } from '../components/RemoteServers/ServerProfileForm';
import { ServerProfileList } from '../components/RemoteServers/ServerProfileList';
import { VPNProfileForm } from '../components/RemoteServers/VPNProfileForm';
import { VPNProfileList } from '../components/RemoteServers/VPNProfileList';
import { RemoteServerProfile, VPNProfile } from '../lib/ipc-client';
import { Plus, Server, Lock } from 'lucide-react';

type Tab = 'servers' | 'vpn';
type FormMode = 'view' | 'add' | 'edit';

export function RemoteServersPage() {
  const [activeTab, setActiveTab] = useState<Tab>('servers');
  const [serverFormMode, setServerFormMode] = useState<FormMode>('view');
  const [vpnFormMode, setVpnFormMode] = useState<FormMode>('view');
  const [selectedServerProfile, setSelectedServerProfile] = useState<RemoteServerProfile | null>(null);
  const [selectedVpnProfile, setSelectedVpnProfile] = useState<VPNProfile | null>(null);

  const serverProfiles = useRemoteServerProfiles();
  const vpnProfiles = useVPNProfiles();

  const handleAddServerProfile = () => {
    setSelectedServerProfile(null);
    setServerFormMode('add');
  };

  const handleEditServerProfile = (profile: RemoteServerProfile) => {
    setSelectedServerProfile(profile);
    setServerFormMode('edit');
  };

  const handleSaveServerProfile = async (
    profile: Omit<RemoteServerProfile, 'id' | 'createdAt' | 'updatedAt'>
  ) => {
    if (serverFormMode === 'add') {
      await serverProfiles.addProfile(profile);
    } else if (selectedServerProfile && serverFormMode === 'edit') {
      await serverProfiles.updateProfile({
        ...profile,
        id: selectedServerProfile.id,
        createdAt: selectedServerProfile.createdAt,
        updatedAt: selectedServerProfile.updatedAt,
      });
    }
    setServerFormMode('view');
    setSelectedServerProfile(null);
  };

  const handleAddVpnProfile = () => {
    setSelectedVpnProfile(null);
    setVpnFormMode('add');
  };

  const handleEditVpnProfile = (profile: VPNProfile) => {
    setSelectedVpnProfile(profile);
    setVpnFormMode('edit');
  };

  const handleSaveVpnProfile = async (
    profile: Omit<VPNProfile, 'id' | 'createdAt' | 'updatedAt'>
  ) => {
    if (vpnFormMode === 'add') {
      await vpnProfiles.addProfile(profile);
    } else if (selectedVpnProfile && vpnFormMode === 'edit') {
      await vpnProfiles.updateProfile({
        ...profile,
        id: selectedVpnProfile.id,
        createdAt: selectedVpnProfile.createdAt,
        updatedAt: selectedVpnProfile.updatedAt,
      });
    }
    setVpnFormMode('view');
    setSelectedVpnProfile(null);
  };

  const handleCancelServerForm = () => {
    setServerFormMode('view');
    setSelectedServerProfile(null);
  };

  const handleCancelVpnForm = () => {
    setVpnFormMode('view');
    setSelectedVpnProfile(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-100">Remote Servers</h1>
          <p className="text-slate-400 mt-1">Manage SSH servers and VPN profiles</p>
        </div>
      </div>

      {/* Error Messages */}
      {serverProfiles.error && (
        <div className="bg-red-900/20 border border-red-700 text-red-300 p-3 rounded-lg">
          Server Error: {serverProfiles.error}
        </div>
      )}
      {vpnProfiles.error && (
        <div className="bg-red-900/20 border border-red-700 text-red-300 p-3 rounded-lg">
          VPN Error: {vpnProfiles.error}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-slate-700">
        <div className="flex gap-4">
          <button
            onClick={() => setActiveTab('servers')}
            className={`px-4 py-3 font-medium border-b-2 transition-colors ${
              activeTab === 'servers'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}
          >
            <Server className="w-4 h-4 inline mr-2" />
            Server Profiles
          </button>
          <button
            onClick={() => setActiveTab('vpn')}
            className={`px-4 py-3 font-medium border-b-2 transition-colors ${
              activeTab === 'vpn'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}
          >
            <Lock className="w-4 h-4 inline mr-2" />
            VPN Profiles
          </button>
        </div>
      </div>

      {/* Server Profiles Tab */}
      {activeTab === 'servers' && (
        <div className="space-y-4">
          {serverFormMode === 'view' ? (
            <>
              <button
                onClick={handleAddServerProfile}
                disabled={serverProfiles.loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Server Profile
              </button>
              <ServerProfileList
                profiles={serverProfiles.profiles}
                isLoading={serverProfiles.loading}
                onEdit={handleEditServerProfile}
                onDelete={serverProfiles.deleteProfile}
                onTestConnection={serverProfiles.testConnection}
                onStartServer={serverProfiles.startServer}
              />
            </>
          ) : (
            <ServerProfileForm
              profile={selectedServerProfile}
              vpnProfiles={vpnProfiles.profiles}
              onSave={handleSaveServerProfile}
              onCancel={handleCancelServerForm}
              isLoading={serverProfiles.loading}
            />
          )}
        </div>
      )}

      {/* VPN Profiles Tab */}
      {activeTab === 'vpn' && (
        <div className="space-y-4">
          {vpnFormMode === 'view' ? (
            <>
              <button
                onClick={handleAddVpnProfile}
                disabled={vpnProfiles.loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add VPN Profile
              </button>
              <VPNProfileList
                profiles={vpnProfiles.profiles}
                isLoading={vpnProfiles.loading}
                onEdit={handleEditVpnProfile}
                onDelete={vpnProfiles.deleteProfile}
                onTestConnection={vpnProfiles.testConnection}
              />
            </>
          ) : (
            <VPNProfileForm
              profile={selectedVpnProfile}
              onSave={handleSaveVpnProfile}
              onCancel={handleCancelVpnForm}
              isLoading={vpnProfiles.loading}
            />
          )}
        </div>
      )}
    </div>
  );
}
