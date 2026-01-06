import { useState, useEffect } from 'react';
import { RemoteServerProfile, VPNProfile } from '../../lib/ipc-client';
import { Check, X } from 'lucide-react';

interface ServerProfileFormProps {
  profile?: RemoteServerProfile | null;
  vpnProfiles: VPNProfile[];
  onSave: (profile: Omit<RemoteServerProfile, 'id' | 'createdAt' | 'updatedAt'>) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

export function ServerProfileForm({
  profile,
  vpnProfiles,
  onSave,
  onCancel,
  isLoading = false,
}: ServerProfileFormProps) {
  const [formData, setFormData] = useState({
    name: '',
    sshHost: '',
    sshPort: 22,
    sshUsername: '',
    sshPrivateKey: '',
    vpnProfileId: 0,
    powerOnCommand: '',
    description: '',
  });

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (profile) {
      setFormData({
        name: profile.name,
        sshHost: profile.sshHost,
        sshPort: profile.sshPort,
        sshUsername: profile.sshUsername,
        sshPrivateKey: profile.sshPrivateKey || '',
        vpnProfileId: profile.vpnProfileId || 0,
        powerOnCommand: profile.powerOnCommand || '',
        description: profile.description || '',
      });
    }
  }, [profile]);

  const validate = (): boolean => {
    const errors: Record<string, string> = {};

    if (!formData.name.trim()) errors.name = 'Name is required';
    if (!formData.sshHost.trim()) errors.sshHost = 'SSH host is required';
    if (formData.sshPort < 1 || formData.sshPort > 65535) errors.sshPort = 'Port must be between 1 and 65535';
    if (!formData.sshUsername.trim()) errors.sshUsername = 'SSH username is required';
    if (!formData.sshPrivateKey.trim()) errors.sshPrivateKey = 'SSH private key is required';

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    try {
      setIsSaving(true);
      await onSave({
        name: formData.name,
        sshHost: formData.sshHost,
        sshPort: formData.sshPort,
        sshUsername: formData.sshUsername,
        sshPrivateKey: formData.sshPrivateKey,
        vpnProfileId: formData.vpnProfileId || null,
        powerOnCommand: formData.powerOnCommand || null,
        description: formData.description || null,
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 bg-slate-900 p-6 rounded-lg border border-slate-700">
      <h3 className="text-lg font-semibold text-slate-100">
        {profile ? 'Edit Server Profile' : 'Add New Server Profile'}
      </h3>

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">Name *</label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="e.g., Home NAS, Office Server"
        />
        {validationErrors.name && (
          <p className="text-red-400 text-sm mt-1">{validationErrors.name}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">Description</label>
        <input
          type="text"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Optional description"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">SSH Host *</label>
          <input
            type="text"
            value={formData.sshHost}
            onChange={(e) => setFormData({ ...formData, sshHost: e.target.value })}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="192.168.1.100 or nas.example.com"
          />
          {validationErrors.sshHost && (
            <p className="text-red-400 text-sm mt-1">{validationErrors.sshHost}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">SSH Port *</label>
          <input
            type="number"
            value={formData.sshPort}
            onChange={(e) => setFormData({ ...formData, sshPort: parseInt(e.target.value) })}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="22"
          />
          {validationErrors.sshPort && (
            <p className="text-red-400 text-sm mt-1">{validationErrors.sshPort}</p>
          )}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">SSH Username *</label>
        <input
          type="text"
          value={formData.sshUsername}
          onChange={(e) => setFormData({ ...formData, sshUsername: e.target.value })}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="e.g., root, admin"
        />
        {validationErrors.sshUsername && (
          <p className="text-red-400 text-sm mt-1">{validationErrors.sshUsername}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">SSH Private Key *</label>
        <textarea
          value={formData.sshPrivateKey}
          onChange={(e) => setFormData({ ...formData, sshPrivateKey: e.target.value })}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
          placeholder="-----BEGIN PRIVATE KEY-----
..."
          rows={6}
        />
        {validationErrors.sshPrivateKey && (
          <p className="text-red-400 text-sm mt-1">{validationErrors.sshPrivateKey}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">VPN Profile (Optional)</label>
        <select
          value={formData.vpnProfileId}
          onChange={(e) => setFormData({ ...formData, vpnProfileId: parseInt(e.target.value) || 0 })}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value={0}>None</option>
          {vpnProfiles.map((vp) => (
            <option key={vp.id} value={vp.id}>
              {vp.name} ({vp.vpnType})
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">Power-On Command</label>
        <input
          type="text"
          value={formData.powerOnCommand}
          onChange={(e) => setFormData({ ...formData, powerOnCommand: e.target.value })}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="e.g., /bin/power-on.sh"
        />
      </div>

      <div className="flex gap-3 justify-end">
        <button
          type="button"
          onClick={onCancel}
          disabled={isSaving || isLoading}
          className="px-4 py-2 bg-slate-800 text-slate-100 rounded-md border border-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <X className="w-4 h-4 inline mr-2" />
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSaving || isLoading}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          <Check className="w-4 h-4" />
          {isSaving ? 'Saving...' : 'Save Profile'}
        </button>
      </div>
    </form>
  );
}
