import { useState } from 'react';
import { useServerProfiles, useVPNProfiles } from '../hooks/useRemoteServers';
import { ServerProfileForm } from '../components/RemoteServers/ServerProfileForm';
import { ServerProfileList } from '../components/RemoteServers/ServerProfileList';
import { VPNProfileForm } from '../components/RemoteServers/VPNProfileForm';
import { VPNProfileList } from '../components/RemoteServers/VPNProfileList';
import { Server, Lock } from 'lucide-react';

export function RemoteServersPage() {
  const serverProfiles = useServerProfiles();
  const vpnProfiles = useVPNProfiles();
  const [activeTab, setActiveTab] = useState<'servers' | 'vpn'>('servers');

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Remote Servers</h1>
        <p className="text-gray-600 mt-2">
          Manage and control your remote BaluHost servers with SSH and VPN profiles
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-gray-200">
        <button
          onClick={() => setActiveTab('servers')}
          className={`flex items-center gap-2 px-4 py-3 font-medium border-b-2 transition-colors ${
            activeTab === 'servers'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-600 hover:text-gray-900'
          }`}
        >
          <Server className="w-4 h-4" />
          Servers
        </button>
        <button
          onClick={() => setActiveTab('vpn')}
          className={`flex items-center gap-2 px-4 py-3 font-medium border-b-2 transition-colors ${
            activeTab === 'vpn'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-600 hover:text-gray-900'
          }`}
        >
          <Lock className="w-4 h-4" />
          VPN Profiles
        </button>
      </div>

      {/* Servers Tab */}
      {activeTab === 'servers' && (
        <div className="space-y-6">
          <div className="bg-white border border-gray-200 rounded-lg">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
              <div>
                <h2 className="text-xl font-semibold text-gray-900">Server Profiles</h2>
                <p className="text-sm text-gray-600 mt-1">
                  Add and manage remote BaluHost servers
                </p>
              </div>
              <ServerProfileForm
                vpnProfiles={vpnProfiles.profiles}
                onCreateProfile={serverProfiles.createProfile}
                isLoading={serverProfiles.loading}
              />
            </div>
            {/* Content */}
            <div className="p-6">
              <ServerProfileList
                profiles={serverProfiles.profiles}
                isLoading={serverProfiles.loading}
                onDelete={serverProfiles.deleteProfile}
                onTestConnection={serverProfiles.testConnection}
                onStartServer={serverProfiles.startServer}
              />
            </div>
          </div>
        </div>
      )}

      {/* VPN Tab */}
      {activeTab === 'vpn' && (
        <div className="space-y-6">
          <div className="bg-white border border-gray-200 rounded-lg">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
              <div>
                <h2 className="text-xl font-semibold text-gray-900">VPN Profiles</h2>
                <p className="text-sm text-gray-600 mt-1">
                  Upload and manage VPN configurations for secure connections
                </p>
              </div>
              <VPNProfileForm
                onCreateProfile={vpnProfiles.createProfile}
                isLoading={vpnProfiles.loading}
              />
            </div>
            {/* Content */}
            <div className="p-6">
              <VPNProfileList
                profiles={vpnProfiles.profiles}
                isLoading={vpnProfiles.loading}
                onDelete={vpnProfiles.deleteProfile}
                onTestConnection={vpnProfiles.testConnection}
              />
            </div>
          </div>
        </div>
      )}

      {/* Info Card */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-blue-900 mb-3">Quick Start</h3>
        <ul className="text-sm text-blue-800 space-y-2">
          <li className="flex gap-2">
            <span className="font-semibold">1.</span>
            <span>Create a VPN Profile if you need secure access (optional)</span>
          </li>
          <li className="flex gap-2">
            <span className="font-semibold">2.</span>
            <span>Add a Server Profile with your SSH credentials</span>
          </li>
          <li className="flex gap-2">
            <span className="font-semibold">3.</span>
            <span>Test the connection to verify SSH access</span>
          </li>
          <li className="flex gap-2">
            <span className="font-semibold">4.</span>
            <span>Use "Start Server" to remotely power on your server</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
