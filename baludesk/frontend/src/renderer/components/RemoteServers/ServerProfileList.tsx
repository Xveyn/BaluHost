import { RemoteServerProfile } from '../../lib/ipc-client';
import { Edit2, Trash2, Play, Zap } from 'lucide-react';
import { useState } from 'react';

interface ServerProfileListProps {
  profiles: RemoteServerProfile[];
  isLoading: boolean;
  onEdit: (profile: RemoteServerProfile) => void;
  onDelete: (id: number) => Promise<void>;
  onTestConnection: (id: number) => Promise<{ connected: boolean; message: string }>;
  onStartServer: (id: number) => Promise<void>;
}

export function ServerProfileList({
  profiles,
  isLoading,
  onEdit,
  onDelete,
  onTestConnection,
  onStartServer,
}: ServerProfileListProps) {
  const [deleting, setDeleting] = useState<number | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [starting, setStarting] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, { connected: boolean; message: string }>>({});

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this profile?')) return;

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

  const handleStartServer = async (id: number) => {
    try {
      setStarting(id);
      await onStartServer(id);
      alert('Power-on command sent!');
    } finally {
      setStarting(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-40">
        <div className="text-slate-400">Loading profiles...</div>
      </div>
    );
  }

  if (profiles.length === 0) {
    return (
      <div className="flex justify-center items-center h-40 border-2 border-dashed border-slate-600 rounded-lg">
        <div className="text-slate-400">No server profiles yet</div>
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
                <h4 className="font-semibold text-slate-100">{profile.name}</h4>
                {profile.description && (
                  <p className="text-sm text-slate-400 mt-1">{profile.description}</p>
                )}
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-slate-300">
                  <div>
                    <span className="text-slate-500">Host:</span> {profile.sshHost}:{profile.sshPort}
                  </div>
                  <div>
                    <span className="text-slate-500">User:</span> {profile.sshUsername}
                  </div>
                  {profile.vpnProfileId && (
                    <div className="col-span-2">
                      <span className="text-slate-500">VPN:</span> Profile #{profile.vpnProfileId}
                    </div>
                  )}
                  {profile.powerOnCommand && (
                    <div className="col-span-2">
                      <span className="text-slate-500">Power-On:</span>{' '}
                      <span className="font-mono text-xs">{profile.powerOnCommand}</span>
                    </div>
                  )}
                </div>

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
                  title="Test SSH Connection"
                >
                  <Zap className="w-4 h-4" />
                </button>

                {profile.powerOnCommand && (
                  <button
                    onClick={() => handleStartServer(profile.id)}
                    disabled={starting === profile.id || deleting === profile.id}
                    className="p-2 bg-green-600 hover:bg-green-700 text-white rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    title="Start Remote Server"
                  >
                    <Play className="w-4 h-4" />
                  </button>
                )}

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
