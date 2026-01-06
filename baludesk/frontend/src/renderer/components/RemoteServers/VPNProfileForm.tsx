import { useState, useEffect } from 'react';
import { VPNProfile } from '../../lib/ipc-client';
import { Check, X } from 'lucide-react';

interface VPNProfileFormProps {
  profile?: VPNProfile | null;
  onSave: (profile: Omit<VPNProfile, 'id' | 'createdAt' | 'updatedAt'>) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

const VPN_TYPES = ['OpenVPN', 'WireGuard', 'IPSec', 'L2TP', 'PPTP', 'OpenConnect'];

export function VPNProfileForm({ profile, onSave, onCancel, isLoading = false }: VPNProfileFormProps) {
  const [formData, setFormData] = useState({
    name: '',
    vpnType: 'OpenVPN' as string,
    description: '',
    configContent: '',
    certificate: '',
    privateKey: '',
    autoConnect: false,
  });

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (profile) {
      setFormData({
        name: profile.name,
        vpnType: profile.vpnType,
        description: profile.description || '',
        configContent: profile.configContent || '',
        certificate: profile.certificate || '',
        privateKey: profile.privateKey || '',
        autoConnect: profile.autoConnect || false,
      });
    }
  }, [profile]);

  const validate = (): boolean => {
    const errors: Record<string, string> = {};

    if (!formData.name.trim()) errors.name = 'Name is required';
    if (!formData.vpnType.trim()) errors.vpnType = 'VPN type is required';
    if (!formData.configContent.trim()) errors.configContent = 'VPN configuration is required';

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, field: string) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const content = await file.text();
      setFormData({ ...formData, [field]: content });
    } catch (err) {
      alert('Failed to read file');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    try {
      setIsSaving(true);
      await onSave({
        name: formData.name,
        vpnType: formData.vpnType,
        description: formData.description || null,
        configContent: formData.configContent || null,
        certificate: formData.certificate || null,
        privateKey: formData.privateKey || null,
        autoConnect: formData.autoConnect,
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 bg-slate-900 p-6 rounded-lg border border-slate-700">
      <h3 className="text-lg font-semibold text-slate-100">
        {profile ? 'Edit VPN Profile' : 'Add New VPN Profile'}
      </h3>

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">Name *</label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="e.g., Home VPN, Office VPN"
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

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">VPN Type *</label>
        <select
          value={formData.vpnType}
          onChange={(e) => setFormData({ ...formData, vpnType: e.target.value })}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {VPN_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        {validationErrors.vpnType && (
          <p className="text-red-400 text-sm mt-1">{validationErrors.vpnType}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">VPN Configuration *</label>
        <div className="space-y-2">
          <textarea
            value={formData.configContent}
            onChange={(e) => setFormData({ ...formData, configContent: e.target.value })}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
            placeholder="Paste VPN configuration content here..."
            rows={8}
          />
          <div className="flex gap-2">
            <label className="cursor-pointer">
              <span className="text-sm text-slate-400 hover:text-slate-300">
                or upload .conf/.ovpn file:
              </span>
              <input
                type="file"
                onChange={(e) => handleFileUpload(e, 'configContent')}
                accept=".conf,.ovpn,.cfg,.config"
                className="hidden"
              />
            </label>
          </div>
        </div>
        {validationErrors.configContent && (
          <p className="text-red-400 text-sm mt-1">{validationErrors.configContent}</p>
        )}
      </div>

      <div className="space-y-2">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">Certificate (Optional)</label>
          <div className="flex gap-2">
            <textarea
              value={formData.certificate}
              onChange={(e) => setFormData({ ...formData, certificate: e.target.value })}
              className="flex-1 px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-xs"
              placeholder="-----BEGIN CERTIFICATE-----"
              rows={4}
            />
            <label className="cursor-pointer">
              <span className="text-xs text-slate-400 hover:text-slate-300 block">Upload</span>
              <input
                type="file"
                onChange={(e) => handleFileUpload(e, 'certificate')}
                accept=".crt,.pem,.cert"
                className="hidden"
              />
            </label>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">Private Key (Optional)</label>
          <div className="flex gap-2">
            <textarea
              value={formData.privateKey}
              onChange={(e) => setFormData({ ...formData, privateKey: e.target.value })}
              className="flex-1 px-3 py-2 bg-slate-800 border border-slate-600 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-xs"
              placeholder="-----BEGIN PRIVATE KEY-----"
              rows={4}
            />
            <label className="cursor-pointer">
              <span className="text-xs text-slate-400 hover:text-slate-300 block">Upload</span>
              <input
                type="file"
                onChange={(e) => handleFileUpload(e, 'privateKey')}
                accept=".key,.pem"
                className="hidden"
              />
            </label>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 bg-slate-800 p-3 rounded-md border border-slate-700">
        <input
          type="checkbox"
          id="autoConnect"
          checked={formData.autoConnect}
          onChange={(e) => setFormData({ ...formData, autoConnect: e.target.checked })}
          className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
        />
        <label htmlFor="autoConnect" className="text-sm text-slate-300 cursor-pointer">
          Automatically connect when opening Remote Servers
        </label>
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
