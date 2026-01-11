import { VPNProfile } from '../../lib/ipc-client';
import { Edit2, Trash2, Zap } from 'lucide-react';
import { useState } from 'react';

interface VPNProfileListProps {
  profiles: VPNProfile[];
  isLoading: boolean;
  onEdit: (profile: VPNProfile) => void;
  onDelete: (id: number) => Promise<void>;
  onTestConnection: (id: number) => Promise<{ connected: boolean; message: string }>;
}

export function VPNProfileList({
  profiles,
  isLoading,
  onEdit,
  onDelete,
  onTestConnection,
}: VPNProfileListProps) {
  const [deleting, setDeleting] = useState<number | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, { connected: boolean; message: string }>>({});

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this VPN profile?')) return;

    try {
      setDeleting(id);
      await onDelete(id);
    } finally {
      setDeleting(null);
    }
  };

  const handleTestConnection = async (id: number) => {
    try {
      setTesting(id);
      const result = await onTestConnection(id);
      setTestResults({ ...testResults, [id]: result });
      setTimeout(() => {
        setTestResults((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
      }, 5000);
    } finally {
      setTesting(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-40">
        <div className="text-slate-400">Loading VPN profiles...</div>
      </div>
    );
  }

  if (profiles.length === 0) {
    return (
      <div className="flex justify-center items-center h-40 border-2 border-dashed border-slate-600 rounded-lg">
        <div className="text-slate-400">No VPN profiles yet</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {profiles.map((profile) => {
        const testResult = testResults[profile.id];
        return (
          <div
            key={profile.id}
            className="bg-slate-900 border border-slate-700 rounded-lg p-4 hover:border-slate-600 transition-colors"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <h4 className="font-semibold text-slate-100">{profile.name}</h4>
                  <span className="px-2 py-1 bg-blue-900 text-blue-300 text-xs rounded-full font-medium">
                    {profile.vpnType}
                  </span>
                  {profile.autoConnect && (
                    <span className="px-2 py-1 bg-green-900 text-green-300 text-xs rounded-full font-medium">
                      Auto-Connect
                    </span>
                  )}
                </div>
                {profile.description && (
                  <p className="text-sm text-slate-400 mt-1">{profile.description}</p>
                )}

                {profile.configContent && (
                  <div className="mt-3 p-2 bg-slate-800 rounded border border-slate-700">
                    <p className="text-xs text-slate-500 mb-1">Configuration Preview:</p>
                    <pre className="text-xs text-slate-400 overflow-auto max-h-20 font-mono whitespace-pre-wrap break-words">
                      {profile.configContent.substring(0, 200)}
                      {profile.configContent.length > 200 ? '...' : ''}
                    </pre>
                  </div>
                )}

                {testResult && (
                  <div
                    className={`mt-3 p-2 rounded text-sm ${
                      testResult.connected
                        ? 'bg-green-900/20 border border-green-700 text-green-300'
                        : 'bg-red-900/20 border border-red-700 text-red-300'
                    }`}
                  >
                    {testResult.message}
                  </div>
                )}
              </div>

              <div className="flex gap-2 ml-4">
                <button
                  onClick={() => handleTestConnection(profile.id)}
                  disabled={testing === profile.id || deleting === profile.id}
                  className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Test VPN Connection"
                >
                  <Zap className="w-4 h-4" />
                </button>

                <button
                  onClick={() => onEdit(profile)}
                  disabled={deleting === profile.id}
                  className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Edit Profile"
                >
                  <Edit2 className="w-4 h-4" />
                </button>

                <button
                  onClick={() => handleDelete(profile.id)}
                  disabled={deleting === profile.id}
                  className="p-2 bg-red-900 hover:bg-red-800 text-red-300 rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Delete Profile"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
