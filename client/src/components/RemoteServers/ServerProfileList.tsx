import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Power,
  Trash2,
  Network,
  Loader2,
  Clock,
  ChevronRight,
} from 'lucide-react';
import * as api from '../../api/remote-servers';

interface ServerProfileListProps {
  profiles: api.ServerProfile[];
  isLoading?: boolean;
  onTestConnection?: (id: number) => Promise<api.SSHConnectionTest>;
  onStartServer?: (id: number) => Promise<api.ServerStartResponse>;
  onDelete?: (id: number) => Promise<void>;
}

export function ServerProfileList({
  profiles,
  isLoading = false,
  onTestConnection,
  onStartServer,
  onDelete,
}: ServerProfileListProps) {
  const { t } = useTranslation('remoteServers');
  const [testingId, setTestingId] = useState<number | null>(null);
  const [startingId, setStartingId] = useState<number | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  const handleDelete = async (id: number, name: string) => {
    if (window.confirm(t('servers.deleteConfirm', { name }))) {
      try {
        setDeleteConfirm(id);
        await onDelete?.(id);
      } finally {
        setDeleteConfirm(null);
      }
    }
  };

  const handleTest = async (id: number) => {
    setTestingId(id);
    try {
      await onTestConnection?.(id);
    } finally {
      setTestingId(null);
    }
  };

  const handleStart = async (id: number) => {
    setStartingId(id);
    try {
      await onStartServer?.(id);
    } finally {
      setStartingId(null);
    }
  };

  if (profiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4">
        <div className="text-center max-w-md">
          <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <ChevronRight className="w-6 h-6 text-gray-400" />
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">{t('servers.noProfiles')}</h3>
          <p className="text-sm text-gray-600">
            {t('servers.noProfilesDescription')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {profiles.map((profile) => (
        <div
          key={profile.id}
          className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
        >
          {/* Profile Header */}
          <div className="flex items-start justify-between mb-3">
            <div className="flex-1 min-w-0">
              <h3 className="text-base font-semibold text-gray-900 truncate">{profile.name}</h3>
              <p className="text-sm text-gray-600 mt-1">
                {profile.ssh_username}@{profile.ssh_host}:{profile.ssh_port}
              </p>
            </div>
            {profile.vpn_profile_id && (
              <span className="ml-2 px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded">
                VPN
              </span>
            )}
          </div>

          {/* Power-On Command */}
          {profile.power_on_command && (
            <div className="mb-3 p-2 bg-gray-50 rounded text-xs font-mono text-gray-700 truncate">
              {profile.power_on_command}
            </div>
          )}

          {/* Last Used */}
          {profile.last_used && (
            <div className="mb-3 text-xs text-gray-500 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {t('servers.lastUsed')}: {new Date(profile.last_used).toLocaleString()}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => handleTest(profile.id)}
              disabled={isLoading || testingId === profile.id}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={t('servers.testConnection')}
            >
              {testingId === profile.id ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Network className="w-4 h-4" />
              )}
              {t('servers.test')}
            </button>

            <button
              onClick={() => handleStart(profile.id)}
              disabled={isLoading || startingId === profile.id}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-green-100 text-green-700 rounded hover:bg-green-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={t('servers.startRemote')}
            >
              {startingId === profile.id ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Power className="w-4 h-4" />
              )}
              {t('servers.start')}
            </button>

            <button
              onClick={() => handleDelete(profile.id, profile.name)}
              disabled={isLoading || deleteConfirm === profile.id}
              className="ml-auto flex items-center gap-2 px-3 py-2 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={t('servers.deleteProfile')}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
