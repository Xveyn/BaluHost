import React, { useMemo } from 'react';
import { Globe, AlertCircle, Zap } from 'lucide-react';
import { useRemoteServerProfiles } from '../../hooks/useRemoteServerProfiles';
import { useServerOnlineStatus } from '../../hooks/useServerOnlineStatus';
import type { RemoteServerProfile } from '../../types/RemoteServerProfile';

interface ServerSelectorProps {
  selectedProfileId: number | null;
  onSelectProfile: (profile: RemoteServerProfile) => void;
  onManualMode?: () => void;
}

/**
 * Server Selector dropdown component for login screen
 * Shows saved Remote Server Profiles with online status indicators
 */
export function ServerSelector({ selectedProfileId, onSelectProfile, onManualMode }: ServerSelectorProps) {
  const { profiles, loading, error } = useRemoteServerProfiles();
  const { statusMap, isLoading: statusLoading, getStatus } = useServerOnlineStatus(profiles, 5000);

  const selectedProfile = useMemo(
    () => profiles.find(p => p.id === selectedProfileId),
    [profiles, selectedProfileId]
  );

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-3 bg-slate-800 border border-slate-700 rounded-lg">
        <div className="animate-spin">
          <Zap size={16} className="text-slate-400" />
        </div>
        <span className="text-sm text-slate-400">Loading servers...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 p-3 bg-red-900/20 border border-red-700/50 rounded-lg">
        <AlertCircle size={16} className="text-red-400" />
        <span className="text-sm text-red-400">{error}</span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-slate-300">
        Remote Server
      </label>
      
      {profiles.length === 0 ? (
        <div className="p-3 bg-slate-800 border border-slate-700 rounded-lg text-center">
          <p className="text-sm text-slate-400">
            No saved servers. <button
              onClick={onManualMode}
              className="text-blue-400 hover:text-blue-300 underline"
            >
              Enter URL manually
            </button>
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <select
            value={selectedProfileId ?? ''}
            onChange={(e) => {
              const profile = profiles.find(p => p.id === Number(e.target.value));
              if (profile) onSelectProfile(profile);
            }}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm
              focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 cursor-pointer"
          >
            <option value="">Select a server...</option>
            {profiles.map((profile) => {
              const status = getStatus(profile.id);
              const isOnline = status?.online ?? false;
              const lastUsed = profile.lastUsed 
                ? new Date(profile.lastUsed).toLocaleDateString() 
                : 'Never';
              
              return (
                <option key={profile.id} value={profile.id}>
                  {profile.name} ({isOnline ? '●' : '○'}) - {profile.sshHost}
                </option>
              );
            })}
          </select>

          {/* Server List with Status */}
          <div className="space-y-2">
            {profiles.map((profile) => {
              const status = getStatus(profile.id);
              const isOnline = status?.online ?? false;
              const isSelected = selectedProfileId === profile.id;

              return (
                <button
                  key={profile.id}
                  onClick={() => onSelectProfile(profile)}
                  className={`w-full px-3 py-2 text-left rounded-lg border transition-all
                    ${isSelected
                      ? 'bg-blue-900/40 border-blue-500/50 ring-1 ring-blue-500/50'
                      : 'bg-slate-800/50 border-slate-700 hover:border-slate-600'
                    }
                  `}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${
                          isOnline ? 'bg-green-400' : 'bg-slate-500'
                        } ${isOnline ? 'animate-pulse' : ''}`} />
                        <span className="font-medium text-slate-100">{profile.name}</span>
                        {statusLoading && selectedProfileId === profile.id && (
                          <Zap size={12} className="animate-spin text-slate-400" />
                        )}
                      </div>
                      <div className="text-xs text-slate-400 mt-1">
                        {profile.sshHost}:{profile.sshPort} • {profile.sshUsername}
                      </div>
                      {status?.errorMessage && !isOnline && (
                        <div className="text-xs text-red-400 mt-1 flex items-center gap-1">
                          <AlertCircle size={10} />
                          {status.errorMessage}
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-slate-400 text-right">
                      {isOnline ? (
                        <span className="text-green-400 font-medium">Online</span>
                      ) : (
                        <span className="text-slate-500">Offline</span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Manual Entry Link */}
          <button
            onClick={onManualMode}
            className="w-full text-xs text-slate-400 hover:text-slate-300 py-1"
          >
            Or enter server URL manually
          </button>
        </div>
      )}
    </div>
  );
}
