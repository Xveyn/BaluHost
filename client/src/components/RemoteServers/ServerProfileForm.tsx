import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Loader2, X } from 'lucide-react';
import * as api from '../../api/remote-servers';

interface ServerProfileFormProps {
  vpnProfiles: api.VPNProfile[];
  onCreateProfile: (data: api.ServerProfileCreate) => Promise<api.ServerProfile>;
  isLoading?: boolean;
}

export function ServerProfileForm({ vpnProfiles, onCreateProfile, isLoading = false }: ServerProfileFormProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [sshHost, setSshHost] = useState('');
  const [sshPort, setSshPort] = useState('22');
  const [sshUsername, setSshUsername] = useState('root');
  const [sshKey, setSshKey] = useState('');
  const [vpnId, setVpnId] = useState<string>('');
  const [powerOnCommand, setPowerOnCommand] = useState('systemctl start baluhost-backend');
  const [loading, setLoading] = useState(false);
  const { t } = useTranslation('remoteServers');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const data: api.ServerProfileCreate = {
        name,
        ssh_host: sshHost,
        ssh_port: parseInt(sshPort),
        ssh_username: sshUsername,
        ssh_private_key: sshKey,
        vpn_profile_id: vpnId ? parseInt(vpnId) : undefined,
        power_on_command: powerOnCommand || undefined,
      };

      await onCreateProfile(data);
      
      // Reset form
      setName('');
      setSshHost('');
      setSshPort('22');
      setSshUsername('root');
      setSshKey('');
      setVpnId('');
      setPowerOnCommand('systemctl start baluhost-backend');
      setOpen(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        disabled={isLoading}
      >
        <Plus className="w-4 h-4" />
        {t('servers.addServer')}
      </button>

      {open && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-md">
            {/* Header */}
            <div className="flex items-center justify-between border-b px-6 py-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">{t('servers.addServerProfile')}</h2>
                <p className="text-sm text-gray-600 mt-1">{t('servers.addServerProfileDescription')}</p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {/* Profile Name */}
              <div>
                <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('servers.profileName')} <span className="text-red-500">*</span>
                </label>
                <input
                  id="name"
                  type="text"
                  placeholder={t('servers.profileNamePlaceholder')}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* SSH Host & Port */}
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label htmlFor="host" className="block text-sm font-medium text-gray-700 mb-1">
                    {t('servers.sshHost')} <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="host"
                    type="text"
                    placeholder="192.168.1.100"
                    value={sshHost}
                    onChange={(e) => setSshHost(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label htmlFor="port" className="block text-sm font-medium text-gray-700 mb-1">
                    {t('servers.port')} <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="port"
                    type="number"
                    placeholder="22"
                    value={sshPort}
                    onChange={(e) => setSshPort(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              {/* SSH Username */}
              <div>
                <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('servers.sshUsername')} <span className="text-red-500">*</span>
                </label>
                <input
                  id="username"
                  type="text"
                  placeholder="root"
                  value={sshUsername}
                  onChange={(e) => setSshUsername(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* SSH Private Key */}
              <div>
                <label htmlFor="key" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('servers.sshPrivateKey')} <span className="text-red-500">*</span>
                </label>
                <textarea
                  id="key"
                  placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----"
                  value={sshKey}
                  onChange={(e) => setSshKey(e.target.value)}
                  required
                  rows={6}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-xs"
                />
              </div>

              {/* VPN Profile */}
              <div>
                <label htmlFor="vpn" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('servers.vpnProfile')}
                </label>
                <select
                  id="vpn"
                  value={vpnId}
                  onChange={(e) => setVpnId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="">{t('common.none')}</option>
                  {vpnProfiles.map((profile) => (
                    <option key={profile.id} value={profile.id.toString()}>
                      {profile.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Power-On Command */}
              <div>
                <label htmlFor="command" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('servers.powerOnCommand')}
                </label>
                <input
                  id="command"
                  type="text"
                  placeholder="systemctl start baluhost-backend"
                  value={powerOnCommand}
                  onChange={(e) => setPowerOnCommand(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  {t('common.cancel')}
                </button>
                <button
                  type="submit"
                  disabled={loading || isLoading}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading || isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
                  {t('servers.createProfile')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
