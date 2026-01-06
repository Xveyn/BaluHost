import { useState } from 'react';
import {
  Trash2,
  Loader2,
  Shield,
  RefreshCw,
  ChevronRight,
} from 'lucide-react';
import * as api from '../../api/remote-servers';

interface VPNProfileListProps {
  profiles: api.VPNProfile[];
  isLoading?: boolean;
  onTestConnection?: (id: number) => Promise<api.VPNConnectionTest>;
  onDelete?: (id: number) => Promise<void>;
}

export function VPNProfileList({
  profiles,
  isLoading = false,
  onTestConnection,
  onDelete,
}: VPNProfileListProps) {
  const [testingId, setTestingId] = useState<number | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  const handleTest = async (id: number) => {
    setTestingId(id);
    try {
      await onTestConnection?.(id);
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (window.confirm(`Delete VPN profile "${name}"? This cannot be undone.`)) {
      try {
        setDeleteConfirm(id);
        await onDelete?.(id);
      } finally {
        setDeleteConfirm(null);
      }
    }
  };

  const getVpnTypeColor = (type: string) => {
    switch (type) {
      case 'openvpn':
        return 'bg-blue-100 text-blue-700';
      case 'wireguard':
        return 'bg-purple-100 text-purple-700';
      default:
        return 'bg-gray-100 text-gray-700';
    }
  };

  if (profiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4">
        <div className="text-center max-w-md">
          <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <ChevronRight className="w-6 h-6 text-gray-400" />
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No VPN Profiles</h3>
          <p className="text-sm text-gray-600">
            Add your first VPN profile to connect to remote networks securely.
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
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-base font-semibold text-gray-900 truncate">{profile.name}</h3>
                <span className={`px-2 py-1 text-xs font-medium rounded ${getVpnTypeColor(profile.vpn_type)}`}>
                  {profile.vpn_type.toUpperCase()}
                </span>
                {profile.auto_connect && (
                  <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-700 rounded flex items-center gap-1">
                    <Shield className="w-3 h-3" />
                    Auto
                  </span>
                )}
              </div>
              {profile.description && (
                <p className="text-sm text-gray-600">{profile.description}</p>
              )}
            </div>
          </div>

          {/* Dates */}
          <div className="mb-3 text-xs text-gray-500 space-y-1">
            <p>Created: {new Date(profile.created_at).toLocaleString()}</p>
            <p>Updated: {new Date(profile.updated_at).toLocaleString()}</p>
          </div>

          {/* Actions */}
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => handleTest(profile.id)}
              disabled={isLoading || testingId === profile.id}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Validate VPN configuration"
            >
              {testingId === profile.id ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              Validate
            </button>

            <button
              onClick={() => handleDelete(profile.id, profile.name)}
              disabled={isLoading || deleteConfirm === profile.id}
              className="ml-auto flex items-center gap-2 px-3 py-2 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Delete profile"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
