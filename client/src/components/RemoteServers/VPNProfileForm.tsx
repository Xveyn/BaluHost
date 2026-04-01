import { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Upload, Loader2, X } from 'lucide-react';
import * as api from '../../api/remote-servers';

interface VPNProfileFormProps {
  onCreateProfile: (formData: FormData) => Promise<api.VPNProfile>;
  isLoading?: boolean;
}

export function VPNProfileForm({ onCreateProfile, isLoading = false }: VPNProfileFormProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [vpnType, setVpnType] = useState<'openvpn' | 'wireguard' | 'custom'>('openvpn');
  const [description, setDescription] = useState('');
  const [autoConnect, setAutoConnect] = useState(false);
  const [configFile, setConfigFile] = useState<File | null>(null);
  const [certFile, setCertFile] = useState<File | null>(null);
  const [keyFile, setKeyFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const { t } = useTranslation('remoteServers');

  const configInputRef = useRef<HTMLInputElement>(null);
  const certInputRef = useRef<HTMLInputElement>(null);
  const keyInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!configFile) return;

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('name', name);
      formData.append('vpn_type', vpnType);
      formData.append('description', description);
      formData.append('auto_connect', autoConnect.toString());
      formData.append('config_file', configFile);

      if (certFile) {
        formData.append('certificate_file', certFile);
      }
      if (keyFile) {
        formData.append('private_key_file', keyFile);
      }

      await onCreateProfile(formData);

      // Reset form
      setName('');
      setVpnType('openvpn');
      setDescription('');
      setAutoConnect(false);
      setConfigFile(null);
      setCertFile(null);
      setKeyFile(null);
      setOpen(false);
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (setter: (f: File | null) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setter(file);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        disabled={isLoading}
      >
        <Plus className="w-4 h-4" />
        {t('vpn.addProfile')}
      </button>

      {open && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-lg w-full max-w-md my-8">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
              <div>
                <h2 className="text-lg font-semibold text-white">{t('vpn.addProfile')}</h2>
                <p className="text-sm text-slate-400 mt-1">{t('vpn.addProfileDescription')}</p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {/* Profile Name */}
              <div>
                <label htmlFor="name" className="block text-sm font-medium text-slate-300 mb-1">
                  {t('vpn.profileName')} <span className="text-red-500">*</span>
                </label>
                <input
                  id="name"
                  type="text"
                  placeholder={t('vpn.profileNamePlaceholder')}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-slate-700 bg-slate-800 text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
              </div>

              {/* VPN Type */}
              <div>
                <label htmlFor="type" className="block text-sm font-medium text-slate-300 mb-1">
                  {t('vpn.type')} <span className="text-red-500">*</span>
                </label>
                <select
                  id="type"
                  value={vpnType}
                  onChange={(e) => setVpnType(e.target.value as 'openvpn' | 'wireguard' | 'custom')}
                  className="w-full px-3 py-2 border border-slate-700 bg-slate-800 text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                >
                  <option value="openvpn">OpenVPN</option>
                  <option value="wireguard">WireGuard</option>
                  <option value="custom">Custom</option>
                </select>
              </div>

              {/* Description */}
              <div>
                <label htmlFor="description" className="block text-sm font-medium text-slate-300 mb-1">
                  {t('vpn.description')}
                </label>
                <input
                  id="description"
                  type="text"
                  placeholder={t('vpn.descriptionPlaceholder')}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-700 bg-slate-800 text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
              </div>

              {/* Config File Upload */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('vpn.configFile')} <span className="text-red-500">*</span>
                </label>
                <div
                  onClick={() => configInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-600 rounded-lg p-4 cursor-pointer hover:border-sky-500 hover:bg-sky-500/10 transition-colors"
                >
                  <div className="flex items-center justify-center gap-2">
                    <Upload className="w-4 h-4 text-slate-500" />
                    <span className="text-sm text-slate-400">
                      {configFile ? configFile.name : t('vpn.clickToUploadConfig')}
                    </span>
                  </div>
                  <input
                    ref={configInputRef}
                    type="file"
                    hidden
                    onChange={handleFileChange(setConfigFile)}
                    accept=".ovpn,.conf"
                  />
                </div>
              </div>

              {/* Certificate File Upload */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('vpn.certificate')}
                </label>
                <div
                  onClick={() => certInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-600 rounded-lg p-4 cursor-pointer hover:border-sky-500 hover:bg-sky-500/10 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-slate-400 flex items-center gap-2">
                      <Upload className="w-4 h-4" />
                      {certFile ? certFile.name : t('vpn.clickToUploadCert')}
                    </span>
                    {certFile && (
                      <X
                        className="w-4 h-4 cursor-pointer text-slate-500 hover:text-red-400"
                        onClick={(e) => {
                          e.stopPropagation();
                          setCertFile(null);
                        }}
                      />
                    )}
                  </div>
                  <input
                    ref={certInputRef}
                    type="file"
                    hidden
                    onChange={handleFileChange(setCertFile)}
                    accept=".crt,.pem,.cert"
                  />
                </div>
              </div>

              {/* Private Key File Upload */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('vpn.privateKey')}
                </label>
                <div
                  onClick={() => keyInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-600 rounded-lg p-4 cursor-pointer hover:border-sky-500 hover:bg-sky-500/10 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-slate-400 flex items-center gap-2">
                      <Upload className="w-4 h-4" />
                      {keyFile ? keyFile.name : t('vpn.clickToUploadKey')}
                    </span>
                    {keyFile && (
                      <X
                        className="w-4 h-4 cursor-pointer text-slate-500 hover:text-red-400"
                        onClick={(e) => {
                          e.stopPropagation();
                          setKeyFile(null);
                        }}
                      />
                    )}
                  </div>
                  <input
                    ref={keyInputRef}
                    type="file"
                    hidden
                    onChange={handleFileChange(setKeyFile)}
                    accept=".key,.pem"
                  />
                </div>
              </div>

              {/* Auto-connect Checkbox */}
              <div className="flex items-center gap-2">
                <input
                  id="auto"
                  type="checkbox"
                  checked={autoConnect}
                  onChange={(e) => setAutoConnect(e.target.checked)}
                  className="w-4 h-4 border border-slate-600 rounded focus:ring-2 focus:ring-sky-500 bg-slate-800 cursor-pointer"
                />
                <label htmlFor="auto" className="text-sm text-slate-300 cursor-pointer">
                  {t('vpn.autoConnect')}
                </label>
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex-1 px-4 py-2 border border-slate-600 text-slate-300 rounded-lg hover:bg-slate-800 transition-colors"
                >
                  {t('common.cancel')}
                </button>
                <button
                  type="submit"
                  disabled={loading || isLoading || !configFile}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {(loading || isLoading) && <Loader2 className="w-4 h-4 animate-spin" />}
                  {t('vpn.createProfile')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
