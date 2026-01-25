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
    <div className="space-y-6 sm:space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Remote Servers</h1>
        <p className="text-slate-400 mt-1 sm:mt-2 text-xs sm:text-sm">
          Manage and control your remote BaluHost servers with SSH and VPN profiles
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
        <div className="flex gap-1 sm:gap-2 border-b border-slate-700/50 min-w-max sm:min-w-0">
          <button
            onClick={() => setActiveTab('servers')}
            className={`flex items-center gap-2 px-3 sm:px-4 py-3 font-medium border-b-2 transition-colors min-h-[44px] touch-manipulation ${
              activeTab === 'servers'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Server className="w-4 h-4" />
            <span className="text-sm">Servers</span>
          </button>
          <button
            onClick={() => setActiveTab('vpn')}
            className={`flex items-center gap-2 px-3 sm:px-4 py-3 font-medium border-b-2 transition-colors min-h-[44px] touch-manipulation ${
              activeTab === 'vpn'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Lock className="w-4 h-4" />
            <span className="text-sm">VPN Profiles</span>
          </button>
        </div>
      </div>

      {/* Servers Tab */}
      {activeTab === 'servers' && (
        <div className="space-y-4 sm:space-y-6">
          <div className="rounded-xl border border-slate-800/60 bg-slate-900/60 overflow-hidden">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4 border-b border-slate-800/60 px-4 sm:px-6 py-4">
              <div>
                <h2 className="text-lg sm:text-xl font-semibold text-white">Server Profiles</h2>
                <p className="text-xs sm:text-sm text-slate-400 mt-1">
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
            <div className="p-4 sm:p-6">
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
        <div className="space-y-4 sm:space-y-6">
          <div className="rounded-xl border border-slate-800/60 bg-slate-900/60 overflow-hidden">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4 border-b border-slate-800/60 px-4 sm:px-6 py-4">
              <div>
                <h2 className="text-lg sm:text-xl font-semibold text-white">VPN Profiles</h2>
                <p className="text-xs sm:text-sm text-slate-400 mt-1">
                  Upload and manage VPN configurations for secure connections
                </p>
              </div>
              <VPNProfileForm
                onCreateProfile={vpnProfiles.createProfile}
                isLoading={vpnProfiles.loading}
              />
            </div>
            {/* Content */}
            <div className="p-4 sm:p-6">
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
      <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 p-4 sm:p-6">
        <h3 className="text-base sm:text-lg font-semibold text-sky-300 mb-3">Quick Start</h3>
        <ul className="text-xs sm:text-sm text-sky-200/80 space-y-2">
          <li className="flex gap-2">
            <span className="font-semibold text-sky-300">1.</span>
            <span>Create a VPN Profile if you need secure access (optional)</span>
          </li>
          <li className="flex gap-2">
            <span className="font-semibold text-sky-300">2.</span>
            <span>Add a Server Profile with your SSH credentials</span>
          </li>
          <li className="flex gap-2">
            <span className="font-semibold text-sky-300">3.</span>
            <span>Test the connection to verify SSH access</span>
          </li>
          <li className="flex gap-2">
            <span className="font-semibold text-sky-300">4.</span>
            <span>Use "Start Server" to remotely power on your server</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
